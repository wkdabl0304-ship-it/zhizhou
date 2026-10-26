"""模型配置全链路回归：真实临时 PostgreSQL、认证、接口、执行快照与迁移约束。"""

import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.core.errors.codes import ErrorCode
from app.models import ChatTurn, Conversation, ProviderConfiguration
from app.schemas.model_config import ProviderConfigurationPatch, DefaultUpdate, ModelPatch
from tests.support.postgres import account, open_runtime, send
from tests.support.fakes.chat import StubChatModel
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from app.llm.providers.failures import ProviderFailure

pytestmark = [pytest.mark.postgres, pytest.mark.anyio]
PREFIX = "/api/model-config"


async def test_empty_configuration_startup_and_authenticated_catalog(postgres_settings):
    """无模型时认证和配置接口可用，聊天返回 503 且不生成任何业务历史。"""
    async with open_runtime(postgres_settings, configured=False) as runtime:
        client = runtime.client
        assert (await client.get(PREFIX + "/catalog/providers")).status_code == 401
        _, headers = await account(runtime.auth)
        providers = await client.get(PREFIX + "/catalog/providers", headers=headers)
        assert {item["provider"] for item in providers.json()["data"]} == {"openai", "anthropic", "deepseek", "bailian"}
        response = await client.get(PREFIX + "/catalog/models?provider=deepseek", headers=headers)
        assert {item["model_id"] for item in response.json()["data"]} == {"deepseek-flash", "deepseek-v4-pro"}
        assert (await client.get(PREFIX + "/default", headers=headers)).json()["data"]["model_configuration_id"] is None
        response = await client.post("/api/chat", json={"message": "你好"}, headers=headers)
        assert response.status_code == 503 and response.json()["code"] == ErrorCode.MODEL_NOT_CONFIGURED.code
        async with runtime.database.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(ChatTurn)) == 0
            assert await session.scalar(select(func.count()).select_from(Conversation)) == 0


async def test_crud_versions_references_and_global_role_access(postgres_settings):
    """普通用户和管理员共享配置，版本冲突和删除引用均不能损坏已有默认。"""
    async with open_runtime(postgres_settings, configured=False) as runtime:
        _, user_headers = await account(runtime.auth)
        _, admin_headers = await account(runtime.auth, "super_admin")
        client = runtime.client
        secret = "private-new-test-key"
        response = await client.post(PREFIX + "/provider-configurations", headers=user_headers, json={
            "name": "官方供应商配置", "provider": "deepseek", "api_format": "chat_completions",
            "endpoint_config": {"endpoint_id": "official"}, "api_key": secret})
        assert response.status_code == 200 and response.json()["code"] == 0, response.text
        provider_configuration = response.json()["data"]
        cid = provider_configuration["id"]
        assert secret not in response.text and "ciphertext" not in response.text
        assert (await client.get(PREFIX + "/provider-configurations", headers=admin_headers)).json()["data"][0]["id"] == cid
        response = await client.post(PREFIX + "/models", headers=admin_headers, json={
            "name": "深入思考", "provider_configuration_id": cid, "catalog_model_id": "deepseek:deepseek-flash",
            "reasoning": {"mode": "effort", "effort": "max"}})
        assert response.status_code == 200 and response.json()["code"] == 0, response.text
        model = response.json()["data"]
        mid = model["id"]
        assert model["provider_configuration_id"] == cid
        filtered = await client.get(PREFIX + "/models", headers=user_headers,
                                    params={"provider_configuration_id": cid})
        assert [item["id"] for item in filtered.json()["data"]] == [mid]
        missing = await client.get(PREFIX + "/models", headers=user_headers,
                                   params={"provider_configuration_id": str(uuid4())})
        assert missing.status_code == 404
        assert missing.json()["code"] == ErrorCode.PROVIDER_CONFIGURATION_NOT_FOUND.code
        assert missing.json()["message"] == "供应商配置不存在"
        selected = await client.put(PREFIX + "/default", headers=user_headers, json={"version": 1, "model_configuration_id": mid})
        assert selected.json()["data"]["version"] == 2
        for path, version in (("provider-configurations/" + cid, 1), ("models/" + mid, 1)):
            blocked = await client.delete(PREFIX + "/" + path, params={"version": version}, headers=user_headers)
            assert blocked.status_code == 409 and blocked.json()["code"] == ErrorCode.MODEL_CONFIG_IN_USE.code
        # 并发更新使用同一旧版本，恰好一个成功；整个配置写入在数据库中串行校验。
        responses = await asyncio.gather(*[
            client.patch(PREFIX + "/models/" + mid, headers=user_headers, json={"version": 1, "name": name})
            for name in ("甲方案", "乙方案")])
        assert sorted(response.status_code for response in responses) == [200, 409]
        patched = await client.patch(PREFIX + "/provider-configurations/" + cid, headers=user_headers, json={"version": 1, "name": "改名供应商配置"})
        assert patched.json()["data"]["version"] == 2
        async with runtime.database.sessions() as session:
            row = await session.get(ProviderConfiguration, cid)
            assert row.credential_revision == 1
            assert secret not in row.api_key_ciphertext
            assert runtime.model_config.secrets.decrypt(row.api_key_ciphertext).get_secret_value() == secret
        await client.put(PREFIX + "/default", headers=admin_headers, json={"version": 2, "model_configuration_id": None})
        assert (await client.delete(PREFIX + "/models/" + mid, params={"version": 2}, headers=user_headers)).json()["code"] == 0
        assert (await client.delete(PREFIX + "/provider-configurations/" + cid, params={"version": 2}, headers=user_headers)).json()["code"] == 0
        assert (await client.get(PREFIX + "/models/" + mid, headers=user_headers)).status_code == 404


async def test_invalid_inputs_and_provider_configuration_update_rollback(postgres_settings):
    """无效组合、空密钥、未知字段和不兼容供应商配置变更均被拒绝且不留下部分修改。"""
    async with open_runtime(postgres_settings) as runtime:
        _, headers = await account(runtime.auth)
        provider_configuration = (await runtime.model_config.list_provider_configurations())[0]
        model = (await runtime.model_config.list_models())[0]
        for changes in ({"api_key": None}, {"api_key": " "}, {"provider": "openai"}, {"base_url": "https://evil.invalid"}):
            response = await runtime.client.patch(f"{PREFIX}/provider-configurations/{provider_configuration.id}", headers=headers, json={"version": 1} | changes)
            assert response.status_code == 422
        for body in ({"reasoning": {"mode": "effort", "effort": "medium"}}, {"max_output_tokens": 999999}, {"reasoning": {"mode": "off", "hidden": True}}):
            response = await runtime.client.patch(f"{PREFIX}/models/{model.id}", headers=headers, json={"version": 1} | body)
            assert response.status_code == 422
        assert (await runtime.model_config.get_model(model.id)).version == 1
        # 模型所属供应商不能通过目录 ID 越过供应商配置归属。
        response = await runtime.client.patch(f"{PREFIX}/models/{model.id}", headers=headers,
            json={"version": 1, "catalog_model_id": "openai:gpt-6-astra"})
        assert response.status_code == 422
        assert (await runtime.model_config.get_provider_configuration(provider_configuration.id)).version == 1


async def test_snapshot_change_key_rotation_smoke_test_and_chat_persistence(postgres_settings):
    """原快照不随配置修改变化；后续聊天使用新版本并持久化无密钥执行信息。"""
    async with open_runtime(postgres_settings) as runtime:
        service = runtime.model_config
        before = await service.snapshot()
        await service.patch_model(before.configuration_id, ModelPatch(version=1, reasoning={"mode": "off"}))
        await service.patch_provider_configuration(before.provider_configuration_id, ProviderConfigurationPatch(version=1, api_key="rotated-test-key"))
        after = await service.snapshot()
        assert before.origin != after.origin and before.credential_revision == 1 and after.credential_revision == 2
        assert before.parameters["extra_body"]["thinking"]["type"] == "enabled"
        assert after.parameters["extra_body"]["thinking"]["type"] == "disabled"
        _, headers = await account(runtime.auth)
        result = await runtime.client.post(f"{PREFIX}/models/{after.configuration_id}/test", headers=headers)
        assert result.json()["data"]["verified"] == "streaming_text", result.text
        assert result.json()["data"]["provider_configuration_version"] == 2
        async with runtime.database.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(ChatTurn)) == 0
        conversation_id, _ = await send(runtime.client, headers, message="你好")
        await send(runtime.client, headers, message="继续", conversation_id=conversation_id)
        assert runtime.snapshots[-1].model_version == 2
        async with runtime.database.sessions() as session:
            rows = list(await session.scalars(select(ChatTurn)))
            assert len(rows) == 2
            assert all(row.model_snapshot["model_version"] == 2 for row in rows)
            assert all(row.model_snapshot["provider_configuration_id"] == str(after.provider_configuration_id) for row in rows)
            assert all(row.model_snapshot["provider_configuration_version"] == 2 for row in rows)
            assert "rotated-test-key" not in str([row.model_snapshot for row in rows])


async def test_model_migration_constraints_and_empty_singleton(postgres_settings):
    """正式迁移建立单例、外键和参数约束，直接写库也不能绕过基本结构限制。"""
    async with open_runtime(postgres_settings, configured=False) as runtime:
        async with runtime.database.sessions() as session:
            assert await session.scalar(text("SELECT version FROM chat_model_settings WHERE id = 1")) == 1
        for statement in (
            "INSERT INTO chat_model_settings (id) VALUES (2)",
            "INSERT INTO model_configurations (id, provider_configuration_id, name, catalog_model_id, reasoning) VALUES ('%s', '%s', 'bad', 'x', '{}')" % (uuid4(), uuid4()),
        ):
            with pytest.raises(IntegrityError):
                async with runtime.database.sessions.begin() as session:
                    await session.execute(text(statement))


async def test_inflight_turn_keeps_snapshot_and_next_turn_sees_update(postgres_settings):
    """当前轮保持旧快照；固定值变化后续聊先拒绝，用户重选后采用新版本。"""
    entered, release = asyncio.Event(), asyncio.Event()

    class WaitingModel(StubChatModel):
        """由事件显式释放首轮生成，用于验证数据库配置更新和生成可并行。"""

        async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
            """首轮先发正文并等待配置更新，其他轮次直接返回最终回复。"""
            if messages[-1].content == "等待更新":
                yield ChatGenerationChunk(message=AIMessageChunk(content="开始", id="held"))
                entered.set()
                await release.wait()
                yield ChatGenerationChunk(message=AIMessageChunk(content="完成", id="held"))
            else:
                async for chunk in super()._astream(messages, stop=stop, run_manager=run_manager, **kwargs):
                    yield chunk

    async with open_runtime(postgres_settings, WaitingModel()) as runtime:
        _, headers = await account(runtime.auth)
        pending = asyncio.create_task(send(runtime.client, headers, "等待更新"))
        try:
            async with asyncio.timeout(10):
                await entered.wait()
                first = runtime.snapshots[0]
                await runtime.model_config.patch_model(first.configuration_id, ModelPatch(version=1, reasoning={"mode": "off"}))
            release.set()
            conversation_id, _ = await pending
            rejected = await runtime.client.post("/api/chat", headers=headers,
                json={"message": "旧选择不能静默变化", "conversation_id": conversation_id})
            assert rejected.status_code == 422 and rejected.json()["code"] == ErrorCode.REASONING_NOT_ALLOWED.code
            selected = await runtime.client.patch(f"/api/conversations/{conversation_id}/model-selection", headers=headers,
                json={"model_selection_version": 1, "model_selection": {
                    "model_configuration_id": str(first.configuration_id), "reasoning": {"mode": "off"}}})
            assert selected.status_code == 200, selected.text
            await send(runtime.client, headers, "下一轮", conversation_id)
            assert [item.model_version for item in runtime.snapshots] == [1, 2]
            assert first.parameters["extra_body"]["thinking"]["type"] == "enabled"
            async with runtime.database.sessions() as session:
                versions = list(await session.scalars(select(ChatTurn.model_snapshot).order_by(ChatTurn.seq)))
                assert [item["model_version"] for item in versions] == [1, 2]
        finally:
            release.set()
            await asyncio.gather(pending, return_exceptions=True)


async def test_test_endpoint_reports_upstream_auth_without_invalidating_login(postgres_settings, caplog):
    """上游鉴权失败返回业务错误而非登录 401，错误响应和日志均不回显原始密钥。"""
    async with open_runtime(postgres_settings) as runtime:
        _, headers = await account(runtime.auth)
        model = (await runtime.model_config.list_models())[0]

        @asynccontextmanager
        async def rejected(snapshot):
            """只用已脱敏的供应商错误替代外部失败，真实 SDK 转换由协议测试覆盖。"""
            raise ProviderFailure(ErrorCode.MODEL_AUTH_FAILED)
            yield

        runtime.model_config.model_opener = rejected
        response = await runtime.client.post(f"{PREFIX}/models/{model.id}/test", headers=headers)
        assert response.status_code == 200 and response.json()["code"] == ErrorCode.MODEL_AUTH_FAILED.code
        assert "unused-test-key" not in response.text + caplog.text
        assert (await runtime.client.get("/api/auth/me", headers=headers)).status_code == 200


async def test_incompatible_format_update_rolls_back_all_provider_configuration_changes(postgres_settings):
    """供应商配置格式变更若使已有模型不可用，密钥、名称、格式及版本一并回滚。"""
    from app.schemas.model_config import ProviderConfigurationCreate, ModelCreate

    async with open_runtime(postgres_settings, configured=False) as runtime:
        service = runtime.model_config
        provider_configuration = await service.create_provider_configuration(ProviderConfigurationCreate(name="OpenAI 官方", provider="openai", api_format="responses",
            endpoint_config={"endpoint_id": "official"}, api_key="original-key"))
        model = await service.create_model(ModelCreate(name="Sol", provider_configuration_id=provider_configuration.id, catalog_model_id="openai:gpt-6.1-sol"))
        from app.core.errors.exceptions import RequestError
        with pytest.raises(RequestError) as error:
            await service.patch_provider_configuration(provider_configuration.id, ProviderConfigurationPatch(version=1, name="不应保存", api_format="chat_completions", api_key="replacement-key"))
        assert error.value.error_code is ErrorCode.MODEL_CONFIG_IN_USE
        saved = await service.get_provider_configuration(provider_configuration.id)
        assert saved.name == "OpenAI 官方" and saved.api_format == "responses" and saved.version == 1
        snapshot = await service.snapshot(model.id)
        assert snapshot.credential_revision == 1 and snapshot.api_key.get_secret_value() == "original-key"


async def test_unavailable_catalog_keeps_configuration_readable_and_rejects_chat(postgres_settings, monkeypatch):
    """目录升级停用模型时仍可管理原配置，聊天返回 503 且不写入失败轮次。"""
    from app.llm.models.catalog import CATALOG

    async with open_runtime(postgres_settings) as runtime:
        model = (await runtime.model_config.list_models())[0]
        monkeypatch.delitem(CATALOG, model.catalog_model_id)
        saved = await runtime.model_config.get_model(model.id)
        assert saved.available is False and saved.catalog is None
        _, headers = await account(runtime.auth)
        response = await runtime.client.post("/api/chat", headers=headers, json={"message": "不应落库"})
        assert response.status_code == 503 and response.json()["code"] == ErrorCode.MODEL_NOT_CONFIGURED.code
        async with runtime.database.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(ChatTurn)) == 0
        await runtime.model_config.set_default(DefaultUpdate(version=2, model_configuration_id=None))
        await runtime.model_config.delete_model(model.id, 1)


async def test_default_switch_compare_and_set_across_concurrent_requests(postgres_settings):
    """两个客户端同时修改默认时只有一个版本能提交，不会把后提交的旧选择覆盖进去。"""
    async with open_runtime(postgres_settings) as runtime:
        model = (await runtime.model_config.list_models())[0]
        _, headers = await account(runtime.auth)
        responses = await asyncio.gather(*[
            runtime.client.put(PREFIX + "/default", headers=headers,
                               json={"version": 2, "model_configuration_id": selected})
            for selected in (str(model.id), None)])
        assert sorted(response.status_code for response in responses) == [200, 409]
        winner = next(response.json()["data"] for response in responses if response.status_code == 200)
        actual = await runtime.model_config.get_default()
        assert actual.version == 3
        assert (str(actual.model_configuration_id) if actual.model_configuration_id else None) == winner["model_configuration_id"]
