"""模型自动恢复与历史身份回归：真实事务验证兜底顺序、幂等、权限、锁和公开字段。"""

from uuid import UUID

import pytest

from app.schemas.model_config import DefaultUpdate, ModelCreate, ModelPatch
from tests.support.postgres import account, open_runtime, send
from tests.support.sse import parse_events

pytestmark = [pytest.mark.postgres, pytest.mark.anyio]


@pytest.mark.parametrize("use_default", [True, False])
async def test_deleted_selection_recovers_without_losing_history(postgres_settings, use_default):
    """删除原方案后自动选默认或首个有效模型，历史、草稿时间和并发保护保持有效。"""
    async with open_runtime(postgres_settings) as runtime:
        service, client = runtime.model_config, runtime.client
        _, headers = await account(runtime.auth)
        _, other = await account(runtime.auth)
        original = (await service.list_models())[0]
        cid, _ = await send(client, headers)
        replacement = await service.create_model(ModelCreate(name="替代模型", provider_configuration_id=original.provider_configuration_id,
            catalog_model_id="deepseek:deepseek-v4-pro"))
        await service.set_default(DefaultUpdate(version=2, model_configuration_id=replacement.id if use_default else None))
        await service.delete_model(original.id, original.version)
        path = f"/api/conversations/{cid}/model-selection"
        body = {"model_selection_version": 1, "model_selection": None}
        assert (await client.patch(path, headers=other, json=body)).status_code == 404
        async with runtime.conversations.locks.hold(UUID(cid)) as acquired:
            assert acquired
            assert (await client.patch(path, headers=headers, json=body)).json()["code"] == 40901
        before = (await client.get(f"/api/conversations/{cid}", headers=headers)).json()["data"]
        repaired = await client.patch(path, headers=headers, json=body)
        assert repaired.status_code == 200, repaired.text
        data = repaired.json()["data"]
        assert data["model_selection"]["model_configuration_id"] == str(replacement.id)
        assert data["model_selection_version"] == 2 and data["model_selection_issue"] is None
        assert data["last_message_at"] == before["conversation"]["last_message_at"]
        assert (await client.patch(path, headers=headers, json=body)).json()["code"] == 40904
        unchanged = await client.patch(path, headers=headers, json={**body, "model_selection_version": 2})
        assert unchanged.json()["data"]["model_selection_version"] == 2
        _, events = await send(client, headers, conversation_id=cid)
        assert events[0].payload["data"]["model"]["display_name"] == "DeepSeek V4 Pro"
        history = (await client.get(f"/api/conversations/{cid}", headers=headers)).json()["data"]
        assert [turn["model"]["catalog_model_id"] for turn in history["items"]] == [original.catalog_model_id, replacement.catalog_model_id]
        assert set(history["items"][0]["model"]) == {"model_configuration_id", "catalog_model_id", "display_name"}
        await service.patch_model(replacement.id, ModelPatch(version=1, enabled=False))
        failed = await client.patch(path, headers=headers, json={**body, "model_selection_version": 2})
        assert failed.status_code == 503 and failed.json()["code"] == 50301
        current = (await client.get(f"/api/conversations/{cid}", headers=headers)).json()["data"]["conversation"]
        assert current["model_selection_version"] == 2


async def test_reasoning_recovery_prefers_same_configuration(postgres_settings):
    """允许范围收紧后优先使用原方案的新合法默认，恢复不创建聊天轮次。"""
    async with open_runtime(postgres_settings) as runtime:
        _, headers = await account(runtime.auth)
        original = (await runtime.model_config.list_models())[0]
        chosen = {"model_configuration_id": str(original.id), "reasoning": {"mode": "off"}}
        sent = await runtime.client.post("/api/chat", headers=headers, json={"message": "先不思考", "model_selection": chosen})
        cid = parse_events(sent)[0].payload["data"]["conversation_id"]
        await runtime.model_config.patch_model(original.id, ModelPatch(version=1,
            reasoning_policy={"mode": "selectable", "allowed_modes": ["effort"], "effort_options": ["high"]}))
        repaired = await runtime.client.patch(f"/api/conversations/{cid}/model-selection", headers=headers,
            json={"model_selection_version": 1, "model_selection": None})
        assert repaired.json()["data"]["model_selection"] == {"model_configuration_id": str(original.id), "reasoning": {"mode": "effort", "effort": "high"}}
        assert len(runtime.snapshots) == 1
