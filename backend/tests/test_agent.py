"""验证 Agent 对话执行、历史隔离、工具调用、串行化与异常日志。

使用内存 checkpoint、本地模型与调用替身，不请求真实模型或数据库。
"""

from concurrent.futures import ThreadPoolExecutor
import importlib
import logging
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
from app.errors.codes import ErrorCode
from app.errors.exceptions import BusinessError, ServiceError


def test_chat_passes_message_and_thread_and_returns_only_final_text():
    """验证消息与对话标识正确传入图，且仅返回最终助手的纯文本。"""
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
    """对空历史、非助手结尾和空回复分别验证系统异常分类及原始异常链。"""
    graph = Mock()
    graph.invoke.return_value = {"messages": messages}
    with pytest.raises(ServiceError) as error:
        ChatAgent(graph).chat("你好", "thread-1")
    assert error.value.error_code is ErrorCode.CHAT_FAILED
    assert isinstance(error.value.__cause__, ValueError)


def test_failed_call_releases_serialization_lock():
    """先模拟失败再调用成功，验证异常路径释放互斥锁并保留底层原因。"""
    graph = Mock()
    graph.invoke.side_effect = [RuntimeError("model failed"), {"messages": [AIMessage(content="ok")]}]
    agent = ChatAgent(graph)
    with pytest.raises(ServiceError) as error:
        agent.chat("first", "thread")
    assert isinstance(error.value.__cause__, RuntimeError)
    assert str(error.value.__cause__) == "model failed"
    assert agent.chat("second", "thread") == "ok"


def test_complete_agent_calls_are_serialized():
    """并发提交多次调用，确认完整轮次的最大同时执行数为一。"""
    active = 0
    maximum = 0
    counter_lock = Lock()

    def invoke(*args, **kwargs):
        """模拟短暂调用并统计进入与退出数量，供并发测试观察重叠。"""
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
        """返回本地模型类型标识，满足 BaseChatModel 的抽象接口。"""
        return "test-model"

    def bind_tools(self, tools, **kwargs):
        """直接返回当前模型供真实 Agent 图调用；测试工具选择由 _generate 模拟。"""
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        """根据消息历史返回本地助手结果或天气工具请求，无需网络。

        工具结果直接转为回复；其他输入拼接历次用户消息，使测试能观察历史读取。
        """
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
    """使用真实 Agent 图验证同线程续聊、跨线程隔离及重建实例后的历史读取。"""
    saver = InMemorySaver()
    agent = ChatAgent(build_agent(StubChatModel(), [get_weather], saver))
    assert agent.chat("first", "a") == "first"
    assert agent.chat("second", "a") == "first|second"
    assert agent.chat("other", "b") == "other"
    # 新 Agent 实例继续使用相同 checkpoint。
    restored = ChatAgent(build_agent(StubChatModel(), [get_weather], saver))
    assert restored.chat("third", "a") == "first|second|third"


def test_real_agent_graph_invokes_weather_tool():
    """验证真实图能发起工具调用，并把固定天气结果交回助手。"""
    agent = ChatAgent(build_agent(StubChatModel(), [get_weather], InMemorySaver()))
    assert agent.chat("天气", "weather") == "上海今天晴天，温度 25°C"


@pytest.mark.parametrize("failure", [False, True])
def test_chat_logs_context_duration_and_failure_without_chat_body(
    monkeypatch, caplog, failure
):
    """固定时钟后检查成功与失败日志的标识、耗时、级别和正文保护。"""
    module = importlib.import_module("app.agents.agent")
    monkeypatch.setattr(module, "perf_counter", Mock(side_effect=[10.0, 10.25]))
    graph = Mock()
    if failure:
        graph.invoke.side_effect = RuntimeError("provider failed")
    else:
        graph.invoke.return_value = {"messages": [AIMessage(content="private-reply")]}
    with caplog.at_level(logging.INFO, logger=module.__name__):
        if failure:
            with pytest.raises(ServiceError):
                ChatAgent(graph).chat("private-message", "thread")
        else:
            assert ChatAgent(graph).chat("private-message", "thread") == "private-reply"
    records = [record for record in caplog.records if record.name == module.__name__]
    assert len(records) == 1
    assert records[0].thread_id == "thread"
    assert records[0].duration_ms == 250
    assert records[0].levelno == (logging.ERROR if failure else logging.INFO)
    assert bool(records[0].exc_info) is failure
    assert "private-message" not in caplog.text
    assert "private-reply" not in caplog.text


def test_duration_includes_waiting_for_lock(monkeypatch, caplog):
    """用推进时钟的锁替身确认对话耗时包含排队时间。"""
    module = importlib.import_module("app.agents.agent")
    clock = [10.0]
    monkeypatch.setattr(module, "perf_counter", lambda: clock[0])

    class QueuedLock:
        def __enter__(self):
            """模拟获取锁前等待两秒，推进由测试控制的时钟。"""
            clock[0] += 2

        def __exit__(self, *args):
            """提供无副作用的退出钩子，使锁替身可用于 with 语句。"""
            pass

    agent = ChatAgent(Mock(invoke=Mock(return_value={"messages": [AIMessage(content="ok")]})))
    agent._lock = QueuedLock()
    with caplog.at_level(logging.INFO, logger=module.__name__):
        agent.chat("hello", "thread")
    assert caplog.records[-1].duration_ms == 2000


@pytest.mark.parametrize("error", [
    BusinessError(error_code=ErrorCode.BUSINESS_ERROR),
    ServiceError(error_code=ErrorCode.INTERNAL_ERROR),
])
def test_explicit_application_error_is_preserved_and_logged_once(error, caplog):
    """验证已知业务或系统异常保持原对象，且只记录一次正确级别的日志。"""
    graph = Mock()
    graph.invoke.side_effect = error
    with caplog.at_level(logging.WARNING), pytest.raises(type(error)) as caught:
        ChatAgent(graph).chat("private-message", "business-thread")
    assert caught.value is error
    assert error.logged
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.thread_id == "business-thread"
    assert record.duration_ms >= 0
    assert record.levelno == (logging.WARNING if isinstance(error, BusinessError) else logging.ERROR)
    assert bool(record.exc_info) is isinstance(error, ServiceError)
