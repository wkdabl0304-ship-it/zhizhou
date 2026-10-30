"""会话模型选择集成测试：真实路由、事务、版本和执行锁，模型边界使用本地替身。"""

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, func, select

from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import ServiceError
from app.models import ChatTurn, Conversation, ProviderConfiguration
from app.schemas.model_config import DefaultUpdate, ModelCreate, ModelPatch, ProviderConfigurationPatch
from tests.support.postgres import account, open_runtime, send
from tests.support.sse import parse_events

pytestmark = [pytest.mark.postgres, pytest.mark.anyio]
PREFIX = "/api/model-config"
POLICY = {"mode": "selectable", "allowed_modes": ["off", "effort"], "effort_options": ["low", "high"]}


def selection(model_id, reasoning=None):
    """为请求构造独立具体选择，不把测试共享字典传给可变状态。"""
    return {"model_configuration_id": str(model_id), "reasoning": reasoning or {"mode": "effort", "effort": "high"}}


async def patch_selection(runtime, headers, conversation_id, value, version=1):
    """通过正式接口保存指定版本的选择，保留原始响应供异常断言。"""
    return await runtime.client.patch(f"/api/conversations/{conversation_id}/model-selection", headers=headers,
        json={"model_selection_version": version, "model_selection": value})


async def test_options_activation_default_and_management_test(postgres_settings):
    """启停影响可选范围和默认有效性，保留子方案状态与凭据版本，仍允许管理测试。"""
    async with open_runtime(postgres_settings) as runtime:
        client, service = runtime.client, runtime.model_config
        _, headers = await account(runtime.auth, "super_admin")
        assert (await client.get(PREFIX + "/options")).status_code == 401
        initial = (await client.get(PREFIX + "/options", headers=headers)).json()["data"]
        mid = initial["default_selection"]["model_configuration_id"]
        provider = initial["providers"][0]
        pid = provider["provider_configuration_id"]
        assert provider["models"][0]["reasoning_control"] == {"mode": "selectable", "allowed_modes": ["off", "effort"], "effort_options": ["low", "high", "max"], "budget": None, "default": {"mode": "effort", "effort": "high"}}
        assert not any(key in str(initial) for key in ("api_key", "endpoint_config", "base_url", "ciphertext"))
        disabled = await client.patch(f"{PREFIX}/provider-configurations/{pid}", headers=headers, json={"version": 1, "enabled": False})
        assert disabled.json()["data"]["version"] == 2
        assert (await client.get(PREFIX + "/options", headers=headers)).json()["data"] == {"default_selection": None, "providers": []}
        info = (await client.get(PREFIX + "/default", headers=headers)).json()["data"]
        assert info["model_configuration_id"] == mid and info["model"]["available"] and not info["model"]["selectable"]
        rejected = await client.put(PREFIX + "/default", headers=headers, json={"version": 2, "model_configuration_id": mid})
        assert rejected.status_code == 422 and rejected.json()["code"] == 42201
        with pytest.raises(ServiceError) as error:
            await service.snapshot()
        assert error.value.error_code is ErrorCode.MODEL_NOT_CONFIGURED
        tested = await client.post(f"{PREFIX}/models/{mid}/test", headers=headers)
        assert tested.json()["data"]["verified"] == "streaming_text"
        async with runtime.database.sessions() as session:
            row = await session.get(ProviderConfiguration, UUID(pid))
            assert row.credential_revision == 1
        await client.patch(f"{PREFIX}/models/{mid}", headers=headers, json={"version": 1, "enabled": False})
        await client.patch(f"{PREFIX}/provider-configurations/{pid}", headers=headers, json={"version": 2, "enabled": True})
        assert not (await service.get_model(UUID(mid))).enabled
        assert (await client.get(PREFIX + "/options", headers=headers)).json()["data"]["providers"] == []
        await client.patch(f"{PREFIX}/models/{mid}", headers=headers, json={"version": 2, "enabled": True})
        assert (await client.get(PREFIX + "/options", headers=headers)).json()["data"]["default_selection"] == initial["default_selection"]


async def test_new_selection_without_default_is_persisted_and_restored(postgres_settings):
    """无需全局默认也能明确选择；首轮和后续轮返回相同选择，清除默认不影响续聊。"""
    async with open_runtime(postgres_settings) as runtime:
        service, client = runtime.model_config, runtime.client
        _, headers = await account(runtime.auth)
        model = (await service.list_models())[0]
        await service.patch_model(model.id, ModelPatch(version=1, reasoning_policy=POLICY))
        await service.set_default(DefaultUpdate(version=2, model_configuration_id=None))
        chosen = selection(model.id, {"mode": "effort", "effort": "low"})
        response = await client.post("/api/chat", headers=headers, json={"message": "选择低档位", "model_selection": chosen})
        events = parse_events(response)
        assert events[-1].event == "done", response.text
        start = events[0].payload["data"]
        cid = start["conversation_id"]
        assert start["model_selection"] == chosen and start["model_selection_version"] == 1
        assert runtime.snapshots[-1].parameters["reasoning_effort"] == "low"
        await send(client, headers, conversation_id=cid)
        for path in ("/api/conversations", f"/api/conversations/{cid}"):
            data = (await client.get(path, headers=headers)).json()["data"]
            info = data["items"][0] if path == "/api/conversations" else data["conversation"]
            assert info["model_selection"] == chosen and info["model_selection_issue"] is None
        async with runtime.database.sessions() as session:
            turns = list(await session.scalars(select(ChatTurn)))
            assert len(turns) == 2 and all(turn.model_snapshot["reasoning"] == chosen["reasoning"] for turn in turns)
            assert "unused-test-key" not in str([turn.model_snapshot for turn in turns])


async def test_invalid_selection_is_atomic_and_does_not_call_provider(postgres_settings):
    """首轮未知档位、未知方案、预算及禁止字段失败时均不留会话或轮次。"""
    async with open_runtime(postgres_settings) as runtime:
        _, headers = await account(runtime.auth)
        model = (await runtime.model_config.list_models())[0]
        for chosen, code in (
            (selection(model.id, {"mode": "effort", "effort": "invented"}), 42202),
            (selection(uuid4()), 42201),
            (selection(model.id, {"mode": "budget", "budget_tokens": 4096}), 42202),
            (selection(model.id, {"mode": "default"}), 42200),
            ({**selection(model.id), "api_key": "injected"}, 42200),
        ):
            response = await runtime.client.post("/api/chat", headers=headers, json={"message": "不应落库", "model_selection": chosen})
            assert response.status_code == 422 and response.json()["code"] == code, response.text
        assert not runtime.snapshots
        async with runtime.database.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(Conversation)) == 0
            assert await session.scalar(select(func.count()).select_from(ChatTurn)) == 0


async def test_immediate_save_version_ownership_and_busy_guards(postgres_settings):
    """立即保存保持目录时间，版本竞争只允许一个成功，越权和生成锁均拒绝切换。"""
    async with open_runtime(postgres_settings) as runtime:
        user, headers = await account(runtime.auth)
        _, other_headers = await account(runtime.auth, "super_admin")
        model = (await runtime.model_config.list_models())[0]
        await runtime.model_config.patch_model(model.id, ModelPatch(version=1, reasoning_policy=POLICY))
        cid, _ = await send(runtime.client, headers)
        before = (await runtime.client.get(f"/api/conversations/{cid}", headers=headers)).json()["data"]["conversation"]
        low = selection(model.id, {"mode": "effort", "effort": "low"})
        assert (await patch_selection(runtime, other_headers, cid, low)).status_code == 404
        async with runtime.conversations.locks.hold(UUID(cid)) as acquired:
            assert acquired
            assert (await patch_selection(runtime, headers, cid, low)).json()["code"] == 40901
        responses = await asyncio.gather(patch_selection(runtime, headers, cid, low), patch_selection(runtime, headers, cid, low))
        assert sorted(response.status_code for response in responses) == [200, 409]
        after = (await runtime.client.get(f"/api/conversations/{cid}", headers=headers)).json()["data"]["conversation"]
        assert after["model_selection"] == low and after["model_selection_version"] == 2
        assert after["last_message_at"] == before["last_message_at"]
        stale = await patch_selection(runtime, headers, cid, low)
        assert stale.json()["code"] == 40904
        stale_send = await runtime.client.post("/api/chat", headers=headers,
            json={"message": "过期界面", "conversation_id": cid, "model_selection_version": 1})
        assert stale_send.status_code == 409 and stale_send.json()["code"] == 40904
        async with runtime.database.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(ChatTurn)) == 1
        response = await runtime.client.post("/api/chat", headers=headers,
            json={"message": "使用已保存选择", "conversation_id": cid, "model_selection_version": 2})
        assert parse_events(response)[-1].event == "done"
        assert runtime.snapshots[-1].parameters["reasoning_effort"] == "low"
        # 旧客户端省略版本时仍能按当前服务端选择继续，不静默覆盖已有选择。
        await send(runtime.client, headers, conversation_id=cid)
        await runtime.client.delete(f"/api/conversations/{cid}", headers=headers)
        assert (await patch_selection(runtime, headers, cid, low, version=2)).status_code == 404


async def test_policy_shrink_disable_delete_and_reselection(postgres_settings):
    """范围收紧、连接停用和方案删除保留原选择及历史，拒绝续聊直到用户明确重选。"""
    async with open_runtime(postgres_settings) as runtime:
        service, client = runtime.model_config, runtime.client
        _, headers = await account(runtime.auth)
        model = (await service.list_models())[0]
        await service.patch_model(model.id, ModelPatch(version=1, reasoning_policy=POLICY))
        response = await client.post("/api/chat", headers=headers,
            json={"message": "低档位", "model_selection": selection(model.id, {"mode": "effort", "effort": "low"})})
        cid = parse_events(response)[0].payload["data"]["conversation_id"]
        # 超管只允许 high 后，已保存 low 失效，不能静默替换。
        await service.patch_model(model.id, ModelPatch(version=2, reasoning_policy={"mode": "selectable", "allowed_modes": ["effort"], "effort_options": ["high"]}))
        for issue, action in (
            ("reasoning_not_allowed", None),
            ("provider_disabled", "disable"),
            ("model_deleted", "delete"),
        ):
            if action == "disable":
                await service.patch_provider_configuration(model.provider_configuration_id, ProviderConfigurationPatch(version=1, enabled=False))
            if action == "delete":
                await service.set_default(DefaultUpdate(version=2, model_configuration_id=None))
                await service.delete_model(model.id, 3)
            info = (await client.get(f"/api/conversations/{cid}", headers=headers)).json()["data"]
            assert info["conversation"]["model_selection_issue"] == issue and len(info["items"]) == 1
            assert info["conversation"]["model_selection"]["reasoning"]["effort"] == "low"
            rejected = await client.post("/api/chat", headers=headers, json={"message": "不能降级", "conversation_id": cid})
            assert rejected.json()["code"] == (42202 if action is None else 42201)
        assert len(runtime.snapshots) == 1
        await service.patch_provider_configuration(model.provider_configuration_id, ProviderConfigurationPatch(version=2, enabled=True))
        replacement = await service.create_model(ModelCreate(name="替代方案", provider_configuration_id=model.provider_configuration_id,
            catalog_model_id=model.catalog_model_id))
        assert (await patch_selection(runtime, headers, cid, selection(replacement.id))).status_code == 200
        await send(client, headers, conversation_id=cid)
        assert runtime.snapshots[-1].configuration_id == replacement.id


async def test_policy_patch_validation_is_atomic_and_options_are_effective(postgres_settings):
    """策略整体替换，不能保存非法默认、能力或区间；成功后选项提供有效边界。"""
    async with open_runtime(postgres_settings) as runtime:
        client, service = runtime.client, runtime.model_config
        _, headers = await account(runtime.auth, "super_admin")
        model = (await service.list_models())[0]
        for extra in (
            {"enabled": None}, {"reasoning_policy": None},
            {"reasoning_policy": {**POLICY, "effort_options": ["low"]}},
            {"reasoning_policy": {**POLICY, "effort_options": ["high", "medium"]}},
            {"reasoning_policy": {"mode": "selectable", "allowed_modes": ["budget"], "budget": {"min": 1, "max": 4}}},
        ):
            result = await client.patch(f"{PREFIX}/models/{model.id}", headers=headers, json={"version": 1, "name": "不应保存", **extra})
            assert result.status_code == 422, result.text
            saved = await service.get_model(model.id)
            assert saved.version == 1 and saved.name == model.name
        changed = await client.patch(f"{PREFIX}/models/{model.id}", headers=headers, json={"version": 1, "reasoning_policy": POLICY})
        assert changed.json()["data"]["selectable"]
        options = (await client.get(PREFIX + "/options", headers=headers)).json()["data"]
        control = options["providers"][0]["models"][0]["reasoning_control"]
        assert control == {**POLICY, "budget": None, "default": {"mode": "effort", "effort": "high"}}


async def test_legacy_empty_selection_initializes_once_and_directory_batches(postgres_settings):
    """旧会话空选择只初始化一次；目录判断多个选择时只发一次批量配置查询。"""
    async with open_runtime(postgres_settings) as runtime:
        user, headers = await account(runtime.auth)
        model = (await runtime.model_config.list_models())[0]
        async with runtime.database.sessions.begin() as session:
            legacy = Conversation(user_id=user.id, title="旧会话")
            session.add(legacy)
            await session.flush()
            cid = str(legacy.id)
        _, events = await send(runtime.client, headers, conversation_id=cid)
        assert events[0].payload["data"]["model_selection_version"] == 2
        _, events = await send(runtime.client, headers, conversation_id=cid)
        assert events[0].payload["data"]["model_selection_version"] == 2
        await send(runtime.client, headers)
        statements = []

        def capture(connection, cursor, statement, parameters, context, executemany):
            """只记录当前目录查询的 SQL，退出后移除监听，避免影响其他测试。"""
            statements.append(statement)

        event.listen(runtime.database.engine.sync_engine, "before_cursor_execute", capture)
        try:
            listing = await runtime.client.get("/api/conversations", headers=headers)
        finally:
            event.remove(runtime.database.engine.sync_engine, "before_cursor_execute", capture)
        assert len(listing.json()["data"]["items"]) == 2
        assert sum("FROM model_configurations" in statement for statement in statements) == 1
        assert all(item["model_selection"]["model_configuration_id"] == str(model.id) for item in listing.json()["data"]["items"])


async def test_budget_creation_options_and_chat_boundaries(postgres_settings):
    """创建预算方案后上下界均可实际聊天，边界外及关闭选择被拒绝且不增加轮次。"""
    async with open_runtime(postgres_settings, configured=False) as runtime:
        client = runtime.client
        _, headers = await account(runtime.auth, "super_admin")
        created = await client.post(PREFIX + "/provider-configurations", headers=headers, json={
            "name": "Claude 预算", "provider": "anthropic", "api_format": "messages",
            "endpoint_config": {"endpoint_id": "official"}, "api_key": "fake-budget-key", "enabled": True})
        assert created.status_code == 200, created.text
        pid = created.json()["data"]["id"]
        created = await client.post(PREFIX + "/models", headers=headers, json={
            "name": "有限预算", "provider_configuration_id": pid,
            "catalog_model_id": "anthropic:claude-haiku-4-5-20251001", "max_output_tokens": 16384,
            "reasoning": {"mode": "budget", "budget_tokens": 4096},
            "reasoning_policy": {"mode": "selectable", "allowed_modes": ["budget"], "budget": {"min": 1024, "max": 8192}}})
        assert created.status_code == 200, created.text
        mid = created.json()["data"]["id"]
        options = (await client.get(PREFIX + "/options", headers=headers)).json()["data"]
        assert options["default_selection"] is None
        assert options["providers"][0]["models"][0]["reasoning_control"]["budget"] == {"min": 1024, "max": 8192}
        for budget in (1024, 8192):
            result = await client.post("/api/chat", headers=headers,
                json={"message": "有效预算", "model_selection": selection(mid, {"mode": "budget", "budget_tokens": budget})})
            assert parse_events(result)[-1].event == "done", result.text
            assert runtime.snapshots[-1].parameters["thinking"] == {"type": "enabled", "budget_tokens": budget}
        for reasoning in ({"mode": "budget", "budget_tokens": 1023}, {"mode": "budget", "budget_tokens": 8193}, {"mode": "off"}):
            result = await client.post("/api/chat", headers=headers, json={"message": "越界预算", "model_selection": selection(mid, reasoning)})
            assert result.status_code == 422 and result.json()["code"] == 42202
        assert len(runtime.snapshots) == 2
        async with runtime.database.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(ChatTurn)) == 2


async def test_saved_model_disable_unavailable_and_metadata_management(postgres_settings, monkeypatch):
    """停用方案或删除目录项时失效原因准确，目录失效仍允许停用、改名和读取历史。"""
    from app.llm.models.catalog import CATALOG

    async with open_runtime(postgres_settings) as runtime:
        service, client = runtime.model_config, runtime.client
        _, headers = await account(runtime.auth)
        model = (await service.list_models())[0]
        cid, _ = await send(client, headers)
        await service.patch_model(model.id, ModelPatch(version=1, enabled=False))
        info = (await client.get(f"/api/conversations/{cid}", headers=headers)).json()["data"]["conversation"]
        assert info["model_selection_issue"] == "model_disabled"
        await service.patch_model(model.id, ModelPatch(version=2, enabled=True))
        monkeypatch.delitem(CATALOG, model.catalog_model_id)
        info = (await client.get(f"/api/conversations/{cid}", headers=headers)).json()["data"]
        assert info["conversation"]["model_selection_issue"] == "model_unavailable" and len(info["items"]) == 1
        assert (await service.patch_model(model.id, ModelPatch(version=3, name="待修复", enabled=False))).name == "待修复"
        changed = await service.patch_provider_configuration(model.provider_configuration_id, ProviderConfigurationPatch(version=1, enabled=False))
        assert changed.enabled is False and changed.version == 2
