"""PostgreSQL 集成测试：独立临时库验证跨连接锁、并发与遗留轮次恢复。"""

import pytest
from sqlalchemy import update

from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import RequestError
from app.models import ChatTurn
from app.services.conversations import ConversationService
from tests.support.postgres import open_runtime as runtime, account

pytestmark = pytest.mark.postgres


@pytest.mark.anyio
async def test_cross_connection_busy_delete_recovery_and_parallel_conversations(
    postgres_settings,
):
    """验证跨连接会话锁能协调生成、删除和遗留轮次恢复。

    独立服务连接竞争同一锁时互斥，不同会话仍可并发；读取不能误中断
    活跃生成，执行者释放锁后才允许恢复遗留运行状态。
    """

    async with runtime(postgres_settings) as environment:
        database = environment.database
        auth = environment.auth
        service = environment.conversations
        client = environment.client
        user, headers = await account(auth)
        other_service = ConversationService(database)
        async with service.prepare(user.id, "正在生成", None) as prepared:
            conversation_id = prepared.conversation_id
            with pytest.raises(RequestError) as error:
                async with other_service.prepare(
                    user.id, "重复生成", conversation_id
                ):
                    pytest.fail("同会话不应获得第二把执行锁")
            assert error.value.error_code is ErrorCode.CONVERSATION_BUSY
            assert (
                await client.post(
                    "/api/chat",
                    headers=headers,
                    json={
                        "message": "冲突",
                        "conversation_id": str(conversation_id),
                    },
                )
            ).status_code == 409
            assert (
                await client.delete(
                    f"/api/conversations/{conversation_id}", headers=headers
                )
            ).status_code == 409
            content = await other_service.content(
                user.id, conversation_id, 20, None
            )
            assert content.items[0].status == "running"
            await other_service.recover()
            assert (
                await other_service.content(user.id, conversation_id, 20, None)
            ).items[0].status == "running"
            async with other_service.prepare(user.id, "另一个会话", None) as other:
                assert other.conversation_id != conversation_id
        assert (await service.content(user.id, conversation_id, 20, None)).items[
            0
        ].status == "interrupted"
        async with database.sessions.begin() as session:
            await session.execute(
                update(ChatTurn)
                .where(ChatTurn.id == prepared.turn_id)
                .values(status="running", finished_at=None)
            )
        await service.recover()
        assert (await service.content(user.id, conversation_id, 20, None)).items[
            0
        ].status == "interrupted"
