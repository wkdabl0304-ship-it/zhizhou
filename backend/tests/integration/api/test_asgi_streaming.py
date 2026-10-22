"""ASGI 流集成测试：验证断开、发送失败与服务器取消后的异步清理。"""

import asyncio
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from langchain_core.messages import AIMessageChunk

from app.agents.agent import ChatAgent
from app.api.routes.chat import chat
from app.services.conversations import PreparedChat
from tests.support.fakes.services import A, MemoryConversationService


@pytest.mark.anyio
@pytest.mark.parametrize("version", ["2.0", "2.4"])
@pytest.mark.parametrize("interruption", ["waiting", "generating", "send", "server"])
async def test_disconnect_cleans_generator_and_conversation_lock(version, interruption, caplog):
    """各 ASGI 版本均在排队、模型等待、发送失败或服务器取消时等待清理完成。"""

    async with asyncio.timeout(5):
        entered, cleaned, delta_sent = asyncio.Event(), asyncio.Event(), asyncio.Event()

        async def stream(inputs, **kwargs):
            """先输出一段再等待取消，finally 执行可观察的异步清理。"""
            try:
                yield "messages", (AIMessageChunk(content="半段", id="partial"), {"langgraph_node": "model"})
                entered.set()
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0.01)
                cleaned.set()

        agent = ChatAgent(Mock(astream=stream))
        holder = None
        if interruption == "waiting":
            holder = asyncio.create_task(agent.achat("first", A))
            await entered.wait()
        response = await chat(PreparedChat(UUID(A), uuid4(), "next", False), agent, MemoryConversationService())

        async def send(message):
            """观察真实编码后的增量，按场景模拟底层 socket 发送失败。"""
            if b"event: delta" in message.get("body", b""):
                delta_sent.set()
                if interruption == "send":
                    raise OSError("client disconnected")

        async def receive():
            """在模型等待或第二轮排队后发送 disconnect，其他场景等待被取消。"""
            if interruption == "waiting":
                while agent._locks[A].users != 2:
                    await asyncio.sleep(0)
            elif interruption == "generating":
                await entered.wait()
            else:
                await asyncio.Event().wait()
            return {"type": "http.disconnect"}

        task = asyncio.create_task(response({"type": "http", "asgi": {"spec_version": version}}, receive, send))
        try:
            if interruption == "server":
                await entered.wait()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                await task
            if holder:
                assert agent._locks[A].users == 1
                assert not cleaned.is_set()
                holder.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await holder
            else:
                assert delta_sent.is_set()
            assert cleaned.is_set() and agent._locks == {}
        finally:
            # 测试断言失败也不遗留阻塞图或响应任务。
            for pending in (task, holder):
                if pending is not None and not pending.done():
                    pending.cancel()
            await asyncio.gather(*(pending for pending in (task, holder) if pending is not None), return_exceptions=True)
    assert not [record for record in caplog.records if record.exc_info]
