"""会话流集成测试：验证 Agent 增量聚合和最终业务提交时序。"""

import asyncio
from uuid import uuid4

import pytest

from app.agents.agent import ChatAgent
from app.schemas.chat import ChatDelta, ChatResponse
from app.services.conversations import PreparedChat
from tests.support.fakes.chat import GraphStub
from tests.support.fakes.services import MemoryConversationService


@pytest.mark.anyio
async def test_stream_waits_for_final_business_commit_and_coalesces_text():
    """验证聊天只有在最终业务提交完成后才确认成功，并合并相邻正文快照。

    使用可控提交屏障观察 done 的交付时机，避免每个 token 都形成独立历史事件。
    """

    async with asyncio.timeout(5):
        service = MemoryConversationService()
        real_persist = service.persist
        entered, release = asyncio.Event(), asyncio.Event()

        async def persist(prepared, **kwargs):
            """为测试提供可暂停的提交替身，以观察最终结果未落库时的流状态。

            completed 提交先通知测试并等待放行，再委托原内存保存逻辑；
            其他状态不阻塞，不访问真实数据库。
            """
            if kwargs.get("status") == "completed":
                entered.set()
                await release.wait()
            await real_persist(prepared, **kwargs)

        service.persist = persist
        prepared = PreparedChat(uuid4(), uuid4(), "你好", True)
        observed = []

        async def consume():
            """保存流事件，观察完成时序而不依赖真实时间长短。"""
            async for event in service.stream(
                prepared, ChatAgent(GraphStub("你好世界"))
            ):
                observed.append(event)

        task = asyncio.create_task(consume())
        await entered.wait()
        assert any(isinstance(event, ChatDelta) for event in observed)
        assert not any(isinstance(event, ChatResponse) for event in observed)
        assert (
            len(prepared.public_events) == 1
            and prepared.public_events[0]["data"]["text"] == "你好世界"
        )
        release.set()
        await task
        assert isinstance(observed[-1], ChatResponse) and prepared.terminal
