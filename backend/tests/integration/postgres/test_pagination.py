"""PostgreSQL 集成测试：独立临时库验证游标、排序和归属边界。"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import update

from app.models import Conversation
from tests.support.postgres import open_runtime as runtime, account, send

pytestmark = pytest.mark.postgres


@pytest.mark.anyio
async def test_recent_and_history_cursors_ties_scope_and_invalid_values(postgres_settings):
    """验证会话目录和历史的游标分页不会遗漏同时间记录或突破归属范围。

    检查历史向前读取但批内正序展示，并拒绝跨用户、跨会话及非法游标。
    """

    async with runtime(postgres_settings) as environment:
        database = environment.database
        auth = environment.auth
        client = environment.client
        user, headers = await account(auth)
        _, foreign = await account(auth)
        ids = [
            (await send(client, headers, f"输入{index}"))[0] for index in range(4)
        ]
        async with database.sessions.begin() as session:
            await session.execute(
                update(Conversation)
                .where(Conversation.user_id == user.id)
                .values(last_message_at=datetime(2026, 1, 1, tzinfo=UTC))
            )
        first = (
            await client.get("/api/conversations?limit=2", headers=headers)
        ).json()["data"]
        second = (
            await client.get(
                "/api/conversations",
                params={"limit": 2, "cursor": first["next_cursor"]},
                headers=headers,
            )
        ).json()["data"]
        found = [
            item["conversation_id"] for item in first["items"] + second["items"]
        ]
        assert found == sorted(ids, reverse=True) and second["next_cursor"] is None
        assert "total" not in first and "page" not in first
        assert (
            await client.get(
                "/api/conversations",
                params={"cursor": first["next_cursor"]},
                headers=foreign,
            )
        ).status_code == 422
        conversation_id = ids[0]
        for index in range(4):
            await send(client, headers, f"继续{index}", conversation_id)
        cursor = None
        batches = []
        while True:
            params = {"limit": 2}
            if cursor:
                params["cursor"] = cursor
            data = (
                await client.get(
                    f"/api/conversations/{conversation_id}",
                    headers=headers,
                    params=params,
                )
            ).json()["data"]
            batches.append([item["seq"] for item in data["items"]])
            cursor = data["next_cursor"]
            if len(batches) == 1:
                assert (
                    await client.get(
                        f"/api/conversations/{ids[1]}",
                        headers=headers,
                        params={"cursor": cursor},
                    )
                ).status_code == 422
            if cursor is None:
                break
        assert batches == [[4, 5], [2, 3], [1]]
        for params in [
            {"limit": 0},
            {"limit": 101},
            {"cursor": "!"},
            {"cursor": ""},
        ]:
            assert (
                await client.get(
                    "/api/conversations", headers=headers, params=params
                )
            ).status_code == 422
            assert (
                await client.get(
                    f"/api/conversations/{conversation_id}",
                    headers=headers,
                    params=params,
                )
            ).status_code == 422
