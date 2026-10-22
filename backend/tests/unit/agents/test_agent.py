"""Agent 单元测试：通过图替身验证增量、会话锁、收尾与异常日志。"""

import asyncio
import importlib
import logging
from contextlib import aclosing
from unittest.mock import Mock

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage

from app.agents.agent import ChatAgent
from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import BusinessError, ServiceError
from app.schemas.chat import ChatDelta, ChatResponse, ChatToolCall
from tests.support.fakes.chat import GraphStub


@pytest.mark.anyio
async def test_chat_passes_message_thread_and_stream_options():
    """确认图只执行一次，收到原始输入和持久化设置，增量与最终文本一致。"""
    graph = GraphStub("你好\n世界")
    agent = ChatAgent(graph)
    events = [event async for event in agent.astream("你好", "thread-1")]
    assert "".join(event.text for event in events if isinstance(event, ChatDelta)) == graph.reply
    assert events[-1] == ChatResponse(reply=graph.reply, conversation_id="thread-1", message_id="reply-1")
    assert len(graph.calls) == 1
    inputs, options = graph.calls[0]
    assert inputs["messages"] == [HumanMessage(content="你好")]
    assert options["config"]["configurable"] == {"thread_id": "conversation:thread-1"}
    assert len(options["config"]["callbacks"]) == 1
    assert options["stream_mode"] == ["messages", "updates", "custom"]
    assert options["version"] == "v1" and options["durability"] == "sync"
    assert graph.closed and agent._locks == {}


@pytest.mark.anyio
@pytest.mark.parametrize("messages", [[], [HumanMessage(content="你好")], [AIMessage(content="")], [AIMessage(content=" \n")]])
async def test_missing_final_reply_is_an_error(messages):
    """没有有效最终助手文本时抛出安全系统异常，保留原始原因并回收会话锁。"""
    async def stream(*args, **kwargs):
        """模拟图结束时没有有效助手输出的各类状态。"""
        yield "updates", {"model": {"messages": messages}}

    agent = ChatAgent(Mock(astream=stream))
    with pytest.raises(ServiceError) as error:
        await agent.achat("你好", "a")
    assert error.value.error_code is ErrorCode.CHAT_FAILED
    assert isinstance(error.value.__cause__, ValueError)
    assert agent._locks == {}


@pytest.mark.anyio
@pytest.mark.parametrize("reasoning", [
    AIMessageChunk(content="", additional_kwargs={"reasoning_content": "private-thinking"}),
    AIMessageChunk(content=[{"type": "reasoning", "reasoning": "private-thinking"}]),
    AIMessageChunk(content=[{"type": "thinking", "thinking": "private-thinking"}]),
    AIMessageChunk(content=[{"type": "reasoning", "summary": [{"type": "summary_text", "text": "private-thinking"}]}]),
])
async def test_excludes_reasoning_and_preserves_progress_and_final_message_identity(reasoning):
    """推理不进入公开流；正文说明与最终回答分别保留，工具参数碎片不当作正文。"""
    async def stream(*args, **kwargs):
        """模拟工具前说明、思考块、工具参数、工具结果及最终回复。"""
        yield "messages", (AIMessageChunk(content="先查询", id="before"), {"langgraph_node": "model"})
        yield "messages", (reasoning, {"langgraph_node": "model"})
        yield "messages", (AIMessageChunk(content="", tool_call_chunks=[{"name": "get_weather", "args": "private-args", "id": "call", "index": 0}]), {"langgraph_node": "model"})
        yield "updates", {"model": {"messages": [AIMessage(content="先查询", id="before", tool_calls=[{"name": "get_weather", "args": {}, "id": "call"}])]}}
        yield "messages", (ToolMessage(content="private-result", tool_call_id="call"), {"langgraph_node": "tools"})
        yield "messages", (AIMessageChunk(content="最终", id="final"), {"langgraph_node": "model"})
        yield "updates", {"model": {"messages": [AIMessage(content="最终", id="final")]}}

    events = [event async for event in ChatAgent(Mock(astream=stream)).astream("天气", "a")]
    assert [event.text for event in events if isinstance(event, ChatDelta)] == ["先查询", "最终"]
    assert events[-1].reply == "最终"
    assert events[-1].message_id == "final"
    assert "private-thinking" not in str(events)
    assert not any(event.event == "reasoning_delta" for event in events)
    assert [event.tool_call_id for event in events if isinstance(event, ChatToolCall)] == ["call"]
    assert "private-args" not in str(events) and "private-result" not in str(events)


@pytest.mark.anyio
@pytest.mark.parametrize("missing_content", ["", " \n"])
async def test_each_tool_step_has_progress_without_repeating_model_text(missing_content):
    """多次工具往返分别保证正文说明，模型已有正文时不追加兜底，最终正文独立。"""
    async def stream(*args, **kwargs):
        """模拟两个缺少正文的步骤和一个已有正文的步骤，不访问模型或实际工具。"""
        for index, content in enumerate([missing_content, "我接着核对结果。", missing_content]):
            message_id = f"step-{index}"
            if content.strip():
                yield "messages", (AIMessageChunk(content=content, id=message_id), {"langgraph_node": "model"})
            yield "updates", {"model": {"messages": [AIMessage(
                content=content, id=message_id,
                tool_calls=[{"name": "get_weather", "args": {"city": "北京"}, "id": f"call-{index}"}],
            )]}}
            yield "updates", {"tools": {"messages": [ToolMessage(content="结果", tool_call_id=f"call-{index}")]}}
        yield "messages", (AIMessageChunk(content="最终回答", id="final"), {"langgraph_node": "model"})
        yield "updates", {"model": {"messages": [AIMessage(content="最终回答", id="final")]}}

    events = [event async for event in ChatAgent(Mock(astream=stream)).astream("天气", "a")]
    for index in range(3):
        text, call = events[index * 2:index * 2 + 2]
        assert isinstance(text, ChatDelta) and isinstance(call, ChatToolCall)
        assert text.message_id == call.message_id == f"step-{index}"
        assert text.text == ("我接着核对结果。" if index == 1 else "我准备调用 get_weather 获取所需信息。")
    assert events[-2].message_id == events[-1].message_id == "final"
    assert events[-1].reply == "最终回答"
    assert len(events) == 8


@pytest.mark.anyio
async def test_same_thread_fifo_other_threads_concurrent_and_cancelled_waiter():
    """通过事件屏障验证同会话 FIFO、跨会话重叠及取消等待者不会破坏共用锁。"""
    async with asyncio.timeout(5):
        entered = []
        first_started = asyncio.Event()
        release = asyncio.Event()
        other_started = asyncio.Event()

        async def stream(inputs, **kwargs):
            """记录模型开始顺序，第一轮等待显式放行，其他会话立即标记进入。"""
            text = inputs["messages"][0].content
            entered.append(text)
            if text == "first":
                first_started.set()
                await release.wait()
            if text == "other":
                other_started.set()
            yield "updates", {"model": {"messages": [AIMessage(content=text)]}}

        agent = ChatAgent(Mock(astream=stream))
        first = asyncio.create_task(agent.achat("first", "a"))
        await first_started.wait()
        cancelled = asyncio.create_task(agent.achat("cancelled", "a"))
        second = asyncio.create_task(agent.achat("second", "a"))
        third = asyncio.create_task(agent.achat("third", "a"))
        other = asyncio.create_task(agent.achat("other", "b"))
        await other_started.wait()
        assert entered == ["first", "other"]
        assert agent._locks["a"].users == 4
        cancelled.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled
        assert agent._locks["a"].users == 3
        release.set()
        assert await asyncio.gather(first, second, third, other) == ["first", "second", "third", "other"]
        assert entered == ["first", "other", "second", "third"]
        assert agent._locks == {}


@pytest.mark.anyio
async def test_first_delta_precedes_completion_and_early_close_releases_graph():
    """首段在图结束前交付；消费者关闭半途流时等待异步清理并释放会话锁。"""
    async with asyncio.timeout(5):
        cleaned = asyncio.Event()

        async def stream(*args, **kwargs):
            """输出首段后永远等待，finally 异步清理模拟底层资源释放。"""
            try:
                yield "messages", (AIMessageChunk(content="首段", id="partial"), {"langgraph_node": "model"})
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                cleaned.set()

        agent = ChatAgent(Mock(astream=stream))
        async with aclosing(agent.astream("hello", "a")) as events:
            first = await anext(events)
            assert first.text == "首段" and not cleaned.is_set()
            assert agent._locks["a"].lock.locked()
        assert cleaned.is_set() and agent._locks == {}
        agent._agent = GraphStub("恢复")
        assert await agent.achat("again", "a") == "恢复"


@pytest.mark.anyio
async def test_generation_cancellation_is_not_logged_as_failure(caplog):
    """取消正在等待模型的请求，异步 finally 完成且无失败堆栈，随后同会话可用。"""
    async with asyncio.timeout(5):
        started, cleaned = asyncio.Event(), asyncio.Event()

        async def stream(*args, **kwargs):
            """暂停模型并在取消后异步执行清理，帮助检测持续取消造成的清理遗漏。"""
            try:
                started.set()
                await asyncio.Event().wait()
                yield
            finally:
                await asyncio.sleep(0)
                cleaned.set()

        agent = ChatAgent(Mock(astream=stream))
        task = asyncio.create_task(agent.achat("hello", "a"))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cleaned.is_set() and agent._locks == {}
        agent._agent = GraphStub("恢复")
        assert await agent.achat("again", "a") == "恢复"
    assert not [record for record in caplog.records if record.levelno >= logging.WARNING]


@pytest.mark.anyio
@pytest.mark.parametrize("flush_failure", [False, True])
async def test_done_waits_for_checkpoint_flush_and_flush_failure_is_not_success(flush_failure):
    """最终模型更新不等于落库完成；图收尾成功才交付 done，写入失败仍抛出错误。"""
    async with asyncio.timeout(5):
        flushing, release = asyncio.Event(), asyncio.Event()

        async def stream(*args, **kwargs):
            """模拟最终模型已产出，但 checkpoint 尚未完成或最终写入失败。"""
            yield "messages", (AIMessageChunk(content="文本", id="reply"), {"langgraph_node": "model"})
            yield "updates", {"model": {"messages": [AIMessage(content="文本", id="reply")]}}
            flushing.set()
            await release.wait()
            if flush_failure:
                raise RuntimeError("checkpoint failed")

        agent = ChatAgent(Mock(astream=stream))
        async with aclosing(agent.astream("hello", "a")) as events:
            assert isinstance(await anext(events), ChatDelta)
            done = asyncio.create_task(anext(events))
            await flushing.wait()
            assert not done.done()
            assert agent._locks["a"].lock.locked()
            release.set()
            if flush_failure:
                with pytest.raises(ServiceError):
                    await done
            else:
                assert isinstance(await done, ChatResponse)
        assert agent._locks == {}


@pytest.mark.anyio
async def test_duration_includes_async_lock_queue(monkeypatch, caplog):
    """使用可控时钟推进排队时间，验证成功日志包含等待同会话锁的耗时。"""
    module = importlib.import_module("app.agents.agent")
    clock = [10.0]

    def now():
        """返回测试推进的时间，避免真实等待造成不稳定耗时断言。"""
        return clock[0]

    monkeypatch.setattr(module, "perf_counter", now)

    with caplog.at_level(logging.INFO, logger=module.__name__):
        async with asyncio.timeout(5):
            agent = ChatAgent(GraphStub("ok"))
            async with agent._conversation("a"):
                pending = asyncio.create_task(agent.achat("hello", "a"))
                while agent._locks["a"].users != 2:
                    await asyncio.sleep(0)
                clock[0] += 2
            await pending
    assert caplog.records[-1].duration_ms == 2000


@pytest.mark.anyio
@pytest.mark.parametrize("failure", [None, RuntimeError("provider failed"), BusinessError(), ServiceError()])
async def test_logs_duration_error_classification_and_recovery(monkeypatch, caplog, failure):
    """验证成功及各类失败只记录一次耗时日志，保留异常链，失败后可再次调用。"""
    module = importlib.import_module("app.agents.agent")
    monkeypatch.setattr(module, "perf_counter", Mock(side_effect=[10.0, 10.25, 11.0, 11.5]))
    graph = GraphStub("private-reply")
    graph.failure = failure
    agent = ChatAgent(graph)

    with caplog.at_level(logging.INFO, logger=module.__name__):
        if failure:
            with pytest.raises((BusinessError, ServiceError)) as caught:
                await agent.achat("private-message", "a")
            if isinstance(failure, (BusinessError, ServiceError)):
                assert caught.value is failure
            else:
                assert caught.value.__cause__ is failure
        else:
            assert await agent.achat("private-message", "a") == "private-reply"
        assert agent._locks == {}
    records = [record for record in caplog.records if record.name == module.__name__]
    assert len(records) == 1 and records[0].duration_ms == 250
    expected = logging.INFO if failure is None else logging.WARNING if isinstance(failure, BusinessError) else logging.ERROR
    assert records[0].levelno == expected
    assert bool(records[0].exc_info) is (expected == logging.ERROR)
    assert "private-message" not in caplog.text and "private-reply" not in caplog.text
    graph.failure = None
    assert await agent.achat("again", "a") == "private-reply"
