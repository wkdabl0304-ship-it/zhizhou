"""验证工具伴随正文的真实 Agent 流程，以及无工具消息结束本轮的执行约束。

本地脚本模型按预设消息流式输出，使用内存 checkpoint 和演示天气工具；
不连接真实模型或数据库，也不把替身输出当作模型遵守提示词的证明。
"""

import asyncio

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, SystemMessage
from langchain_core.outputs import ChatGenerationChunk
from langgraph.checkpoint.memory import InMemorySaver

from app.agents.agent import ChatAgent
from app.agents.factory import build_agent
from app.agents.prompts import SYSTEM_PROMPT
from app.agents.tools.weather import get_weather
from app.schemas.chat import ChatDelta, ChatResponse, ChatToolCall, ChatToolStart
from chat_fakes import StubChatModel


@pytest.mark.parametrize("with_tools", [False, True])
def test_content_and_tool_calls_share_model_step_and_final_reply_is_separate(with_tools):
    """真实图保留同消息的正文和并行调用；无工具时只调用一次模型并直接交付答案。"""
    async def scenario():
        """执行预设的两次工具往返或直接回答，核对流顺序、提示词注入及持久化内容。"""
        final_text = (
            "北京和上海的演示天气均为晴天、25°C；这些固定数据不能作为实时出行依据。"
            if with_tools else "演示数据用于展示功能，不反映实时天气，出行前需要核对实时信息。"
        )
        responses = [AIMessage(content=final_text, id="final")]
        if with_tools:
            responses = [
                AIMessage(
                    content=(
                        "我会先查询北京和上海的天气，再核对结果是否足以比较，最后整理差异和数据限制。"
                        "本次分别调用天气工具获取两地结果，以便按同类信息进行比较。"
                    ),
                    id="plan",
                    tool_calls=[
                        {"name": "get_weather", "args": {"city": city}, "id": f"weather-{index}"}
                        for index, city in enumerate(["北京", "上海"])
                    ],
                ),
                AIMessage(
                    content=(
                        "两地均返回晴天、25°C，结果来自演示工具，尚不能确认实时差异。"
                        "我会再查询北京以核对返回是否一致，并在最终回答中说明数据限制。"
                    ),
                    id="check",
                    tool_calls=[{"name": "get_weather", "args": {"city": "北京"}, "id": "recheck"}],
                ),
                *responses,
            ]
        model_inputs = []

        class ProgressModel(StubChatModel):
            """在一次模型调用内先流出正文再流出调用块，模拟供应商的混合消息。"""

            async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
                """记录完整输入并拆成两段正文；额外模型调用会越界，使意外循环直接失败。"""
                response = responses[len(model_inputs)]
                model_inputs.append(list(messages))
                midpoint = len(response.text) // 2
                for text in [response.text[:midpoint], response.text[midpoint:]]:
                    yield ChatGenerationChunk(message=AIMessageChunk(content=text, id=response.id))
                if response.tool_calls:
                    yield ChatGenerationChunk(message=AIMessageChunk(
                        content="", id=response.id, tool_calls=response.tool_calls,
                    ))

        graph = build_agent(ProgressModel(), [get_weather], InMemorySaver())
        question = "比较北京和上海的天气" if with_tools else "为什么不能用演示数据判断实时天气？"
        events = [event async for event in ChatAgent(graph).astream(question, "progress")]

        assert len(model_inputs) == len(responses)
        for messages in model_inputs:
            assert isinstance(messages[0], SystemMessage)
            assert messages[0].content == SYSTEM_PROMPT
        for response in responses:
            # 每段原始正文恰好出现一次，不能被兜底覆盖、重复追加或拼进另一模型消息。
            deltas = [event for event in events if isinstance(event, ChatDelta) and event.message_id == response.id]
            assert "".join(event.text for event in deltas) == response.text
            assert len(deltas) == 2
            for call in response.tool_calls:
                call_index = next(index for index, event in enumerate(events)
                                  if isinstance(event, ChatToolCall) and event.tool_call_id == call["id"])
                start_index = next(index for index, event in enumerate(events)
                                   if isinstance(event, ChatToolStart) and event.tool_call_id == call["id"])
                assert all(events.index(delta) < call_index < start_index for delta in deltas)
                assert events[call_index].message_id == response.id
                assert events[call_index].arguments == call["args"]

        assert events[-1] == ChatResponse(reply=final_text, thread_id="progress", message_id="final")
        assert sum(isinstance(event, ChatToolCall) for event in events) == (3 if with_tools else 0)
        state = await graph.aget_state({"configurable": {"thread_id": "progress"}})
        saved = [message for message in state.values["messages"] if isinstance(message, AIMessage)]
        assert [message.text for message in saved] == [response.text for response in responses]
        assert [message.tool_calls for message in saved] == [response.tool_calls for response in responses]

    asyncio.run(asyncio.wait_for(scenario(), 5))
