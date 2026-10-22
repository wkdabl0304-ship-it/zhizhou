"""真实工具图集成测试：验证并发工具、错误、artifact 排除与取消。"""

import asyncio
from contextlib import aclosing

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import ToolException, tool
from langgraph.checkpoint.memory import InMemorySaver

from app.agents.agent import ChatAgent
from app.agents.factory import build_agent
from app.core.errors.exceptions import ServiceError
from app.schemas.chat import ChatDelta, ChatResponse, ChatToolCall, ChatToolEnd, ChatToolError, ChatToolStart
from tests.support.fakes.chat import StubChatModel


class ToolCallingModel(StubChatModel):
    """根据注入的名称列表生成工具请求，工具结束后只回复固定文本。"""

    names: list[str]

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        """首次生成带唯一调用 ID 的工具请求，工具结果返回后结束本轮。"""
        if isinstance(messages[-1], ToolMessage):
            message = AIMessage(content="已完成")
        else:
            message = AIMessage(content="", tool_calls=[
                {"name": name, "args": {}, "id": f"call-{index}"}
                for index, name in enumerate(self.names)
            ])
        return ChatResult(generations=[ChatGeneration(message=message)])


@pytest.mark.anyio
async def test_parallel_tools_report_independent_completion_before_node_finishes():
    """两个工具同时运行，较快工具结束事件立即到达，不等待整个 tools 节点完成。"""

    async with asyncio.timeout(5):
        release_first, release_second = asyncio.Event(), asyncio.Event()
        both_started, second_finished = asyncio.Event(), asyncio.Event()
        observed = []

        @tool
        async def slow_tool() -> str:
            """等待测试放行并返回普通工具结果。"""
            await release_first.wait()
            return "普通工具结果"

        @tool
        async def command_preview() -> str:
            """返回固定命令展示结果，不实际执行系统命令。"""
            await release_second.wait()
            return '{"stdout":"ok","stderr":"","exit_code":0}'

        # metadata 由 BaseTool 持有；命令类别是展示声明，替身不具有系统执行能力。
        command_preview.metadata = {"display_kind": "command"}
        agent = ChatAgent(build_agent(ToolCallingModel(names=["slow_tool", "command_preview"]), [slow_tool, command_preview], InMemorySaver()))

        async def consume():
            """消费真实图的 custom 流，标记 UI 已能收到的开始与完成事件。"""
            async with aclosing(agent.astream("执行工具", "parallel")) as stream:
                async for event in stream:
                    observed.append(event)
                    if len([item for item in observed if isinstance(item, ChatToolStart)]) == 2:
                        both_started.set()
                    if isinstance(event, ChatToolEnd) and event.name == "command_preview":
                        second_finished.set()

        task = asyncio.create_task(consume())
        try:
            await both_started.wait()
            assert len([event for event in observed if isinstance(event, ChatToolCall)]) == 2
            # 模型只返回并行调用时，兜底正文仍在调用和实际执行之前到达。
            assert isinstance(observed[0], ChatDelta)
            assert "slow_tool、command_preview" in observed[0].text
            release_second.set()
            await second_finished.wait()
            assert not any(isinstance(event, ChatToolEnd) and event.name == "slow_tool" for event in observed)
            release_first.set()
            await task
            starts = {event.tool_call_id: event for event in observed if isinstance(event, ChatToolStart)}
            ends = {event.tool_call_id: event for event in observed if isinstance(event, ChatToolEnd)}
            assert set(starts) == set(ends) == {"call-0", "call-1"}
            for call_id in starts:
                assert starts[call_id].run_id == ends[call_id].run_id
                assert starts[call_id].conversation_id == ends[call_id].conversation_id == "parallel"
            assert starts["call-1"].kind == ends["call-1"].kind == "command"
            assert starts["call-0"].kind == "tool"
            assert isinstance(observed[-1], ChatResponse)
            assert agent._locks == {}
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.anyio
@pytest.mark.parametrize("recoverable", [False, True])
async def test_tool_error_has_safe_identity_and_can_be_recovered(recoverable):
    """真实异常与工具自行处理的异常都只发一次安全错误；可恢复失败仍可产生最终回答。"""
    async with asyncio.timeout(5):
        @tool
        def failing_tool() -> str:
            """为测试产生工具失败，不连接外部服务。"""
            if recoverable:
                raise ToolException("private-tool-error")
            raise RuntimeError("private-tool-error")

        failing_tool.handle_tool_error = recoverable
        agent = ChatAgent(build_agent(ToolCallingModel(names=["failing_tool"]), [failing_tool], InMemorySaver()))
        observed = []
        try:
            async for event in agent.astream("失败工具", "a"):
                observed.append(event)
        except ServiceError:
            assert not recoverable
        else:
            assert recoverable
        errors = [event for event in observed if isinstance(event, ChatToolError)]
        starts = [event for event in observed if isinstance(event, ChatToolStart)]
        assert len(errors) == len(starts) == 1
        assert errors[0].tool_call_id == starts[0].tool_call_id == "call-0"
        assert errors[0].run_id == starts[0].run_id
        assert "private-tool-error" not in str(observed)
        assert not any(isinstance(event, ChatToolEnd) for event in observed)
        assert any(isinstance(event, ChatResponse) for event in observed) is recoverable
        assert agent._locks == {}


@pytest.mark.anyio
async def test_tool_artifact_is_not_part_of_public_output():
    """工具正文可以返回给调用方，artifact 仍作为内部对象保存在工具消息中。"""
    @tool(response_format="content_and_artifact")
    def artifact_tool() -> tuple[str, dict]:
        """返回公开正文及内部附件对象，用来验证过程事件只提取 content。"""
        return "公开结果", {"private-artifact": "hidden"}

    agent = ChatAgent(build_agent(ToolCallingModel(names=["artifact_tool"]), [artifact_tool], InMemorySaver()))
    observed = [event async for event in agent.astream("工具", "a")]
    ends = [event for event in observed if isinstance(event, ChatToolEnd)]
    assert ends[0].output == "公开结果"
    assert "private-artifact" not in str(observed)


@pytest.mark.anyio
@pytest.mark.parametrize("name", ["unknown_tool", "get_weather"])
async def test_rejected_tool_call_still_reports_one_safe_error(name):
    """未知工具或缺少必需参数也有工具失败事件，不让调用方一直停留在等待状态。"""
    from app.agents.tools.weather import get_weather

    async with asyncio.timeout(5):
        agent = ChatAgent(build_agent(ToolCallingModel(names=[name]), [get_weather], InMemorySaver()))
        observed = [event async for event in agent.astream("工具", "a")]
        errors = [event for event in observed if isinstance(event, ChatToolError)]
        assert len(errors) == 1
        assert errors[0].tool_call_id == "call-0" and errors[0].name == name
        if name == "unknown_tool":
            assert errors[0].run_id is None
            assert not any(isinstance(event, ChatToolStart) for event in observed)
        assert isinstance(observed[-1], ChatResponse)


@pytest.mark.anyio
async def test_cancel_during_tool_execution_cleans_without_false_completion():
    """工具开始后取消，等待工具 finally 完成并释放会话锁，不伪造 end 或 done。"""
    async with asyncio.timeout(5):
        entered, cleaned = asyncio.Event(), asyncio.Event()
        observed = []

        @tool
        async def waiting_tool() -> str:
            """在取消测试中暂停实际工具执行，并通过异步 finally 标记清理。"""
            try:
                entered.set()
                await asyncio.Event().wait()
                return "unreachable"
            finally:
                await asyncio.sleep(0)
                cleaned.set()

        agent = ChatAgent(build_agent(ToolCallingModel(names=["waiting_tool"]), [waiting_tool], InMemorySaver()))

        async def consume():
            """持续消费过程事件，直至测试取消该任务。"""
            async with aclosing(agent.astream("工具", "a")) as stream:
                async for event in stream:
                    observed.append(event)

        task = asyncio.create_task(consume())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cleaned.is_set() and agent._locks == {}
        assert not any(isinstance(event, (ChatResponse, ChatToolEnd)) for event in observed)
