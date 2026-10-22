"""DeepSeek 协议集成测试：MockTransport 验证正式客户端与真实图的往返。"""

import asyncio
import json

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.agents.agent import ChatAgent
from app.agents.factory import build_agent
from app.agents.models import DeepSeekChatModel
from app.agents.tools.weather import get_weather
from app.schemas.chat import ChatDelta, ChatToolCall, ChatToolEnd, ChatToolStart


@pytest.mark.anyio
async def test_real_model_http_stream_preserves_reasoning_across_tool_and_followup_requests():
    """真实 DeepSeek 解析器接收思考和工具参数碎片，后续请求完整回传历史思考。"""

    async with asyncio.timeout(10):
        requests = []

        async def respond(request):
            """构造 DeepSeek Chat Completions SSE，工具选择、工具后回复和追问分别响应。"""
            body = json.loads(request.content)
            requests.append(body)
            last = body["messages"][-1]
            if last["role"] == "user" and last["content"] == "天气":
                deltas = [
                    {"role": "assistant", "reasoning_content": "先查"},
                    {"reasoning_content": "天气"},
                    {"tool_calls": [{"index": 0, "id": "weather-1", "type": "function", "function": {"name": "get_weather", "arguments": '{"city":'}}]},
                    {"tool_calls": [{"index": 0, "function": {"arguments": '"上海"}'}}]},
                ]
            elif last["role"] == "tool":
                deltas = [{"role": "assistant", "reasoning_content": "整理结果"}, {"content": "上海"}, {"content": "晴"}]
            else:
                deltas = [{"role": "assistant", "reasoning_content": "继续回答"}, {"content": "多轮回复"}]
            chunks = [
                {"id": f"completion-{len(requests)}", "object": "chat.completion.chunk", "created": 1,
                 "model": "deepseek-flash", "choices": [{"index": 0, "delta": delta, "finish_reason": None}]}
                for delta in deltas
            ]
            data = "".join(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n" for chunk in chunks)
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=(data + "data: [DONE]\n\n").encode())

        transport = httpx.MockTransport(respond)
        # 同步客户端只用于满足模型构造契约；图始终走异步客户端。
        # 同步路径始终返回 500，适配器若误用同步 HTTP 就会暴露错误。
        with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500))) as sync_client:
            async with httpx.AsyncClient(transport=transport) as async_client:
                model = DeepSeekChatModel(
                    model="deepseek-flash", api_key="test-key", base_url="https://test.invalid",
                    http_client=sync_client, http_async_client=async_client,
                    extra_body={"thinking": {"type": "enabled"}},
                )
                graph = build_agent(model, [get_weather], InMemorySaver())
                agent = ChatAgent(graph)
                events = [event async for event in agent.astream("天气", "a")]
                assert not any(event.event == "reasoning_delta" for event in events)
                assert "整理结果" not in str(events)
                assert [event.text for event in events if isinstance(event, ChatDelta)] == ["我准备调用 get_weather 获取所需信息。", "上海", "晴"]
                calls = [event for event in events if isinstance(event, ChatToolCall)]
                starts = [event for event in events if isinstance(event, ChatToolStart)]
                ends = [event for event in events if isinstance(event, ChatToolEnd)]
                assert calls[0].arguments == starts[0].arguments == {"city": "上海"}
                assert calls[0].tool_call_id == starts[0].tool_call_id == ends[0].tool_call_id == "weather-1"
                assert events.index(calls[0]) < events.index(starts[0]) < events.index(ends[0])
                assert events[-1].reply == "上海晴"
                state = await graph.aget_state({"configurable": {"thread_id": "conversation:a"}})
                saved = [message for message in state.values["messages"] if isinstance(message, AIMessage)]
                assert [message.additional_kwargs["reasoning_content"] for message in saved] == ["先查天气", "整理结果"]
                assert await agent.achat("继续", "a") == "多轮回复"
                assert len(requests) == 3
                assert all(body["thinking"] == {"type": "enabled"} for body in requests)
                assert requests[1]["messages"][2]["reasoning_content"] == "先查天气"
                previous = [message for message in requests[2]["messages"] if message["role"] == "assistant"]
                assert [message["reasoning_content"] for message in previous] == ["先查天气", "整理结果"]

                # 已有旧消息缺少思考字段时回填空值，不修改原对象或伪造历史思考。
                old = AIMessage(content="旧回复")
                payload = model._get_request_payload([HumanMessage(content="旧问题"), old, ToolMessage(content="结果", tool_call_id="old")])
                assert payload["messages"][1]["reasoning_content"] == ""
                assert old.additional_kwargs == {}
