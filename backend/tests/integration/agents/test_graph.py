"""真实图集成测试：验证内存 checkpoint 的历史延续、工具往返与取消。"""

import asyncio
from typing import Any

import pytest
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from langgraph.checkpoint.memory import InMemorySaver

from app.agents.agent import ChatAgent
from app.agents.factory import build_agent
from app.agents.tools.weather import get_weather
from app.schemas.chat import ChatDelta
from tests.support.fakes.chat import StubChatModel


@pytest.mark.anyio
async def test_real_graph_history_tools_and_restore():
    """真实异步图验证多轮、隔离、重建与工具链，完成事件对应已保存的助手消息。"""
    saver = InMemorySaver()
    graph = build_agent(StubChatModel(), [get_weather], saver)
    agent = ChatAgent(graph)
    assert await agent.achat("first", "a") == "first"
    assert await agent.achat("second", "a") == "first|second"
    assert await agent.achat("other", "b") == "other"
    restored = ChatAgent(build_agent(StubChatModel(), [get_weather], saver))
    assert await restored.achat("third", "a") == "first|second|third"
    events = [event async for event in agent.astream("天气", "weather")]
    assert events[-1].reply == "上海今天晴天，温度 25°C"
    assert next(event for event in events if isinstance(event, ChatDelta)).text == "我准备调用 get_weather 获取所需信息。"
    assert events[0].message_id != events[-1].message_id
    state = await graph.aget_state({"configurable": {"thread_id": "conversation:weather"}})
    assert state.values["messages"][-1].text == events[-1].reply
    assert state.values["messages"][-1].id == events[-1].message_id


@pytest.mark.anyio
async def test_real_graph_cancellation_retains_user_checkpoint_without_partial_answer():
    """真实图取消后保留已保存的用户输入，不把已发出的半段文本伪装为完成回复。"""
    class PausedModel(StubChatModel):
        """首段后暂停的本地模型；事件作为测试依赖传入，不访问真实服务。"""

        entered: Any
        cleaned: Any

        async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
            """先发半段再阻塞，取消时标记模型资源清理已完成。"""
            try:
                yield ChatGenerationChunk(message=AIMessageChunk(content="半段", id="partial"))
                self.entered.set()
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                self.cleaned.set()

    async with asyncio.timeout(5):
        entered, cleaned = asyncio.Event(), asyncio.Event()
        graph = build_agent(PausedModel(entered=entered, cleaned=cleaned), [], InMemorySaver())
        agent = ChatAgent(graph)
        task = asyncio.create_task(agent.achat("保存用户问题", "a"))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        state = await graph.aget_state({"configurable": {"thread_id": "conversation:a"}})
        assert [message.content for message in state.values["messages"]] == ["保存用户问题"]
        assert cleaned.is_set() and agent._locks == {}
