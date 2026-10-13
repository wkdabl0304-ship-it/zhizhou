from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import sleep
from unittest.mock import Mock

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver

from app.agents.agent import ChatAgent
from app.agents.factory import build_agent
from app.agents.tools.weather import get_weather


def test_chat_passes_message_and_thread_and_returns_only_final_text():
    graph = Mock()
    graph.invoke.return_value = {"messages": [
        HumanMessage(content="你好"),
        AIMessage(content=[{"type": "text", "text": "回复"}]),
    ]}
    assert ChatAgent(graph).chat("你好", "thread-1") == "回复"
    args, kwargs = graph.invoke.call_args
    assert len(args[0]["messages"]) == 1
    assert isinstance(args[0]["messages"][0], HumanMessage)
    assert args[0]["messages"][0].content == "你好"
    assert kwargs["config"] == {"configurable": {"thread_id": "thread-1"}}


@pytest.mark.parametrize("messages", [[], [HumanMessage(content="你好")], [AIMessage(content="")]])
def test_missing_final_reply_is_an_error(messages):
    graph = Mock()
    graph.invoke.return_value = {"messages": messages}
    with pytest.raises(ValueError, match="Agent"):
        ChatAgent(graph).chat("你好", "thread-1")


def test_failed_call_releases_serialization_lock():
    graph = Mock()
    graph.invoke.side_effect = [RuntimeError("model failed"), {"messages": [AIMessage(content="ok")]}]
    agent = ChatAgent(graph)
    with pytest.raises(RuntimeError, match="model failed"):
        agent.chat("first", "thread")
    assert agent.chat("second", "thread") == "ok"


def test_complete_agent_calls_are_serialized():
    active = 0
    maximum = 0
    counter_lock = Lock()

    def invoke(*args, **kwargs):
        nonlocal active, maximum
        with counter_lock:
            active += 1
            maximum = max(maximum, active)
        sleep(0.01)
        with counter_lock:
            active -= 1
        return {"messages": [AIMessage(content="ok")]}

    agent = ChatAgent(Mock(invoke=invoke))
    with ThreadPoolExecutor(max_workers=4) as executor:
        replies = list(executor.map(lambda i: agent.chat(str(i), "thread"), range(8)))
    assert replies == ["ok"] * 8
    assert maximum == 1


class StubChatModel(BaseChatModel):
    """运行真实 LangChain 图；用可观察历史和工具调用的本地模型替代网络。"""

    @property
    def _llm_type(self):
        return "test-model"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if isinstance(messages[-1], ToolMessage):
            reply = AIMessage(content=messages[-1].content)
        elif messages[-1].content == "天气":
            reply = AIMessage(content="", tool_calls=[{
                "name": "get_weather", "args": {"city": "上海"}, "id": "weather-1"
            }])
        else:
            reply = AIMessage(content="|".join(
                message.content for message in messages if isinstance(message, HumanMessage)
            ))
        return ChatResult(generations=[ChatGeneration(message=reply)])


def test_real_agent_graph_continues_history_and_isolates_threads():
    saver = InMemorySaver()
    agent = ChatAgent(build_agent(StubChatModel(), [get_weather], saver))
    assert agent.chat("first", "a") == "first"
    assert agent.chat("second", "a") == "first|second"
    assert agent.chat("other", "b") == "other"
    # 新 Agent 实例继续使用相同 checkpoint。
    restored = ChatAgent(build_agent(StubChatModel(), [get_weather], saver))
    assert restored.chat("third", "a") == "first|second|third"


def test_real_agent_graph_invokes_weather_tool():
    agent = ChatAgent(build_agent(StubChatModel(), [get_weather], InMemorySaver()))
    assert agent.chat("天气", "weather") == "上海今天晴天，温度 25°C"
