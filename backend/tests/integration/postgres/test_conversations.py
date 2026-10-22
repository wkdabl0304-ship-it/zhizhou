"""PostgreSQL 集成测试：独立临时库验证会话所有权、公开历史和软删除。"""

from uuid import uuid4

import pytest

from app.agents.agent import checkpoint_key
from tests.support.postgres import open_runtime as runtime, account, send

pytestmark = pytest.mark.postgres


@pytest.mark.anyio
@pytest.mark.parametrize(
    "owner_role,other_role", [("user", "super_admin"), ("super_admin", "user")]
)
async def test_auto_creation_public_history_ownership_and_soft_delete(
    postgres_settings, owner_role, other_role
):
    """验证会话自动创建、历史恢复、所有权隔离与软删除的完整流程。

    使用真实 checkpoint 续聊，核对超级管理员同样不能越权，删除后底层历史仍保留。
    """

    async with runtime(postgres_settings) as environment:
        auth = environment.auth
        graph = environment.graph
        client = environment.client
        _owner, headers = await account(auth, owner_role)
        _, foreign = await account(auth, other_role)
        conversation_id, received = await send(client, headers)
        assert received[0][1]["data"]["is_new"] is True
        for _, payload in received:
            assert payload["data"]["conversation_id"] == conversation_id
        detail = (
            await client.get(
                f"/api/conversations/{conversation_id}", headers=headers
            )
        ).json()["data"]
        turn = detail["items"][0]
        assert (
            turn["status"] == "completed"
            and turn["assistant_content"] == "上海今天晴天，温度 25°C"
        )
        assert [item["event"] for item in turn["public_events"]] == [
            "delta",
            "tool_call",
            "tool_start",
            "tool_end",
        ]
        assert all(
            item["data"]["conversation_id"] == conversation_id
            for item in turn["public_events"]
        )
        _, continued = await send(client, headers, "第二轮", conversation_id)
        assert continued[0][1]["data"]["is_new"] is False
        assert continued[-1][1]["data"]["reply"] == "天气|第二轮"
        assert (await client.get("/api/conversations", headers=foreign)).json()[
            "data"
        ]["items"] == []
        for method, path, body in [
            ("GET", f"/api/conversations/{conversation_id}", None),
            ("DELETE", f"/api/conversations/{conversation_id}", None),
            (
                "POST",
                "/api/chat",
                {"message": "越权", "conversation_id": conversation_id},
            ),
        ]:
            response = await client.request(
                method, path, headers=foreign, json=body
            )
            assert response.status_code == 404 and response.json()["code"] == 40401
        assert (
            await client.post(
                "/api/chat",
                headers=headers,
                json={"message": "不能创建", "conversation_id": str(uuid4())},
            )
        ).status_code == 404
        assert (
            await client.post(
                "/api/chat",
                headers=headers,
                json={"message": "旧协议", "thread_id": conversation_id},
            )
        ).status_code == 422
        assert (
            await client.delete(
                f"/api/conversations/{conversation_id}", headers=headers
            )
        ).json()["code"] == 0
        assert (
            await client.delete(
                f"/api/conversations/{conversation_id}", headers=headers
            )
        ).json()["code"] == 0
        assert (
            await client.get(
                f"/api/conversations/{conversation_id}", headers=headers
            )
        ).status_code == 404
        assert (
            await client.post(
                "/api/chat",
                headers=headers,
                json={"message": "删除后续聊", "conversation_id": conversation_id},
            )
        ).status_code == 404
        assert (await client.get("/api/conversations", headers=headers)).json()[
            "data"
        ]["items"] == []
        snapshot = await graph.aget_state(
            {"configurable": {"thread_id": checkpoint_key(conversation_id)}}
        )
        assert snapshot.values["messages"][-1].text == "天气|第二轮"
