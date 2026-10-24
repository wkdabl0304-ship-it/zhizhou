"""供应商协议集成：真实专用客户端和 Agent 通过模拟 HTTP 完成流、工具及多轮往返。"""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
import json
from uuid import uuid4

import httpx
import httpx2
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import SecretStr
import pytest

from app.agents.agent import checkpoint_key
from app.agents.tools.weather import get_weather
from app.core.errors.codes import ErrorCode
from app.llm.models.policy import resolve_parameters
from app.llm.providers.clients import open_model
from app.llm.providers.failures import ProviderFailure
from app.llm.runtime import ConfiguredChatAgent
from app.llm.types import ModelSnapshot
from app.schemas.model_config import DefaultReasoning


def make_snapshot(provider, api_format, model_id):
    """从正式策略取得参数，用假凭据隔离所有实际模型网络请求。"""
    catalog_id = f"{provider}:{model_id}"
    _, params = resolve_parameters(provider, api_format, catalog_id, DefaultReasoning(), 16384)
    return ModelSnapshot(uuid4(), uuid4(), 1, 1, 1, provider, api_format, catalog_id,
                         "https://test.invalid/v1", params, SecretStr("private-protocol-key"))


def encode_frames(events, *, chat=False):
    """编码供应商 SSE 帧，Chat 使用 data 帧，其他格式保留事件类型。"""
    result = ""
    for event in events:
        if not chat:
            result += f"event: {event['type']}\n"
        result += "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
    if chat:
        result += "data: [DONE]\n\n"
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=result.encode())


def chat_response(model_id, tool):
    """模拟 Chat 文本或碎片工具请求，私有推理字段用于验证公开协议隔离。"""
    deltas = [{"role": "assistant", "reasoning_content": "private-thought"}]
    if tool:
        deltas += [{"content": "我先查询天气。"}, {"tool_calls": [{"index": 0, "id": "weather-1", "type": "function", "function": {"name": "get_weather", "arguments": '{"city":'}}]},
                   {"tool_calls": [{"index": 0, "function": {"arguments": '"上海"}'}}]}]
    else:
        deltas += [{"content": "最终"}, {"content": "回答"}]
    events = [{"id": "chat-1", "object": "chat.completion.chunk", "created": 1, "model": model_id,
               "choices": [{"index": 0, "delta": delta, "finish_reason": None}]} for delta in deltas]
    return encode_frames(events, chat=True)


def anthropic_response(model_id, tool):
    """模拟 Messages 的思考签名、工具参数碎片、正文及结束状态。"""
    events = [{"type": "message_start", "message": {"id": "msg_1", "type": "message", "role": "assistant", "model": model_id,
               "content": [], "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 0}}},
              {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}},
              {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "private-thought"}},
              {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "private-signature"}},
              {"type": "content_block_stop", "index": 0}]
    if tool:
        events += [{"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": "weather-1", "name": "get_weather", "input": {}}},
                   {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": '{"city":"上海"}'}},
                   {"type": "content_block_stop", "index": 1}]
    else:
        events += [{"type": "content_block_start", "index": 1, "content_block": {"type": "text", "text": ""}},
                   {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "最终回答"}},
                   {"type": "content_block_stop", "index": 1}]
    events += [{"type": "message_delta", "delta": {"stop_reason": "tool_use" if tool else "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 8}},
               {"type": "message_stop"}]
    return encode_frames(events)


def responses_response(model_id, tool):
    """模拟 Responses 原生事件，使工具参数与最终 response 经过正式 SDK 解析。"""
    response = {"id": "resp_1", "object": "response", "created_at": 1, "status": "in_progress", "model": model_id,
                "output": [], "parallel_tool_calls": True, "tool_choice": "auto", "tools": [], "error": None,
                "incomplete_details": None, "instructions": None, "metadata": {}, "temperature": 1, "top_p": 1,
                "usage": {"input_tokens": 1, "output_tokens": 8, "total_tokens": 9,
                          "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 2}}}
    events = [{"type": "response.created", "sequence_number": 0, "response": response.copy()}]
    if tool:
        item = {"type": "function_call", "id": "fc_1", "call_id": "weather-1", "name": "get_weather", "arguments": "", "status": "in_progress"}
        events += [{"type": "response.output_item.added", "output_index": 0, "item": item.copy()},
                   {"type": "response.function_call_arguments.delta", "output_index": 0, "item_id": "fc_1", "delta": '{"city":"上海"}'}]
        item.update(arguments='{"city":"上海"}', status="completed")
    else:
        item = {"type": "message", "id": "msg_1", "role": "assistant", "status": "in_progress", "content": []}
        events += [{"type": "response.output_item.added", "output_index": 0, "item": item.copy()},
                   {"type": "response.content_part.added", "output_index": 0, "item_id": "msg_1", "content_index": 0, "part": {"type": "output_text", "text": "", "annotations": []}},
                   {"type": "response.output_text.delta", "output_index": 0, "item_id": "msg_1", "content_index": 0, "delta": "最终回答"},
                   {"type": "response.output_text.done", "output_index": 0, "item_id": "msg_1", "content_index": 0, "text": "最终回答"}]
        item.update(status="completed", content=[{"type": "output_text", "text": "最终回答", "annotations": []}])
    events.append({"type": "response.output_item.done", "output_index": 0, "item": item.copy()})
    response.update(status="completed", output=[item])
    events.append({"type": "response.completed", "response": response})
    return encode_frames(events)


@pytest.mark.anyio
@pytest.mark.parametrize("provider,api_format,model_id", [
    ("deepseek", "chat_completions", "deepseek-flash"),
    ("bailian", "chat_completions", "qwen3.8-max"),
    ("openai", "chat_completions", "gpt-5.6-terra"),
    ("openai", "responses", "gpt-6.1-sol"),
    ("anthropic", "messages", "claude-sonnet-5"),
])
async def test_specialized_protocol_stream_tools_and_followup(provider, api_format, model_id):
    """五种供应商/格式组合均完成工具往返和下一轮，公开事件不含内部推理。"""
    snapshot = make_snapshot(provider, api_format, model_id)
    requests, clients = [], []

    async def respond(request):
        """记录实际请求并按调用顺序提供工具请求、工具后回复和续聊。"""
        body = json.loads(request.content)
        requests.append(body)
        assert body["model"] == model_id
        if api_format == "messages":
            assert request.headers["x-api-key"] == "private-protocol-key"
            response = anthropic_response(model_id, len(requests) == 1)
            return httpx2.Response(200, headers=dict(response.headers), content=response.content)
        assert request.headers["authorization"] == "Bearer private-protocol-key"
        if api_format == "responses":
            return responses_response(model_id, len(requests) == 1)
        return chat_response(model_id, len(requests) == 1)

    @asynccontextmanager
    async def opener(actual):
        """将模拟 HTTP 注入正式客户端，记录底层连接以验证轮次结束清理。"""
        transport = httpx2.MockTransport(respond) if provider == "anthropic" else httpx.MockTransport(respond)
        async with open_model(actual, transport=transport) as model:
            clients.append(model._owned_async if provider == "anthropic" else model.http_async_client)
            yield model

    saver = InMemorySaver()
    agent = ConfiguredChatAgent(saver, [get_weather], model_opener=opener)
    async with asyncio.timeout(15):
        events = [event async for event in agent.astream("天气", "protocol", snapshot=snapshot)]
        assert events[-1].reply == "最终回答"
        assert {"tool_call", "tool_start", "tool_end", "done"} <= {event.event for event in events}
        assert "private-thought" not in str(events) and "private-signature" not in str(events)
        assert await agent.achat("继续", "protocol", snapshot=snapshot) == "最终回答"
    assert len(requests) == 3 and all(client.is_closed for client in clients)
    if provider == "deepseek":
        assert requests[1]["messages"][2]["reasoning_content"] == "private-thought"
    elif provider == "bailian":
        assert requests[0]["enable_thinking"] is True and requests[0]["reasoning_effort"] == "xhigh"
    elif api_format == "messages":
        assert "private-signature" in json.dumps(requests[1])
    elif api_format == "responses":
        assert requests[0]["reasoning"]["effort"] == "medium" and requests[0]["store"] is False
        assert any(item["type"] == "function_call_output" for item in requests[1]["input"])


@pytest.mark.anyio
@pytest.mark.parametrize("provider,api_format,model_id", [
    ("deepseek", "chat_completions", "deepseek-flash"),
    ("bailian", "chat_completions", "qwen3.8-max"),
    ("openai", "chat_completions", "gpt-5.6-terra"),
    ("openai", "responses", "gpt-6.1-sol"),
    ("anthropic", "messages", "claude-sonnet-5"),
])
@pytest.mark.parametrize("status,code", [(401, ErrorCode.MODEL_AUTH_FAILED), (429, ErrorCode.MODEL_RATE_LIMITED), (500, ErrorCode.MODEL_TEST_FAILED)])
async def test_sdk_failures_are_safe_and_close_clients(status, code, caplog, provider, api_format, model_id):
    """上游响应即使回显密钥也不会进入异常链或日志，失败后 HTTP 资源关闭。"""
    snapshot = make_snapshot(provider, api_format, model_id)

    async def rejected(request):
        """故意在错误体中回显凭据，验证供应商边界不会记录原始响应。"""
        http = httpx2 if provider == "anthropic" else httpx
        return http.Response(status, json={"error": {"message": "private-protocol-key", "type": "api_error"}})

    with pytest.raises(ProviderFailure) as error:
        transport = httpx2.MockTransport(rejected) if provider == "anthropic" else httpx.MockTransport(rejected)
        async with open_model(snapshot, transport=transport) as model:
            client = model._owned_async if provider == "anthropic" else model.http_async_client
            async for _ in model.astream([HumanMessage(content="测试")]):
                pass
    assert error.value.error_code is code and error.value.__suppress_context__
    assert "private-protocol-key" not in str(error.value) + caplog.text
    assert client.is_closed


@pytest.mark.anyio
async def test_cancelled_real_sdk_stream_closes_transport_and_clients():
    """真实 SDK 等待后续 HTTP 字节时取消，响应流和模型客户端均立即释放。"""
    waiting, visible = asyncio.Event(), asyncio.Event()
    stream_closed = []
    clients = []

    class HeldStream(httpx.AsyncByteStream):
        """首个合法 SSE 后暂停，由取消驱动结束，避免用固定延时判断清理。"""

        async def __aiter__(self):
            """先交付公开文本，再等待测试取消模型请求。"""
            response = chat_response("gpt-5.6-terra", False)
            first_frame = response.content.split(b"\n\n")[1] + b"\n\n"
            yield first_frame
            waiting.set()
            await asyncio.Event().wait()

        async def aclose(self):
            """记录 SDK 确实关闭了底层 HTTP 响应体。"""
            stream_closed.append(True)

    async def respond(request):
        """为正式 SDK 提供挂起的 HTTP 响应，不访问真实模型服务。"""
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=HeldStream())

    @asynccontextmanager
    async def opener(snapshot):
        """记录正式客户端句柄，供取消完成后断言资源关闭。"""
        async with open_model(snapshot, transport=httpx.MockTransport(respond)) as model:
            clients.append(model.http_async_client)
            yield model

    snapshot = make_snapshot("openai", "chat_completions", "gpt-5.6-terra")
    agent = ConfiguredChatAgent(InMemorySaver(), [], model_opener=opener)

    async def consume():
        """持续消费实际 Agent 增量，看到首段时发出明确的可见信号。"""
        async for event in agent.astream("等待", "cancel", snapshot=snapshot):
            if event.event == "delta":
                visible.set()

    task = asyncio.create_task(consume())
    try:
        async with asyncio.timeout(10):
            await waiting.wait()
            await visible.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert stream_closed and clients[0].is_closed
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.anyio
async def test_cross_provider_history_and_credential_rotation_preserve_checkpoint():
    """跨 Claude、Responses、DeepSeek 续聊仅发送兼容历史，原签名仍保存在 checkpoint。"""
    claude = make_snapshot("anthropic", "messages", "claude-sonnet-5")
    openai = make_snapshot("openai", "responses", "gpt-6.1-sol")
    deepseek = make_snapshot("deepseek", "chat_completions", "deepseek-flash")
    requests = []

    @asynccontextmanager
    async def opener(snapshot):
        """为每个目标协议返回正式 SSE，只有首个 Claude 回合发起工具调用。"""
        async def respond(request):
            """记录跨供应商的真实请求体，响应内容保持固定以隔离模型非确定性。"""
            body = json.loads(request.content)
            requests.append((snapshot.provider, body))
            tool = len(requests) == 1
            if snapshot.provider == "anthropic":
                response = anthropic_response(body["model"], tool)
                return httpx2.Response(200, headers=dict(response.headers), content=response.content)
            if snapshot.api_format == "responses":
                return responses_response(body["model"], tool)
            return chat_response(body["model"], tool)

        transport = httpx2.MockTransport(respond) if snapshot.provider == "anthropic" else httpx.MockTransport(respond)
        async with open_model(snapshot, transport=transport) as model:
            yield model

    saver = InMemorySaver()
    agent = ConfiguredChatAgent(saver, [get_weather], model_opener=opener)
    async with asyncio.timeout(20):
        for index, snapshot in enumerate((claude, openai, deepseek, claude, replace(claude, credential_revision=2))):
            assert await agent.achat(f"第{index}轮", "switch", snapshot=snapshot) == "最终回答"
    # 首轮 Claude 有工具往返，因此下一供应商从第 3 次实际请求开始。
    assert "private-signature" not in json.dumps(requests[2:4])
    assert "private-signature" in json.dumps(requests[4])
    assert "private-signature" not in json.dumps(requests[5])
    # 直接读取保存器，确认投影没有回写或删除原始供应商思考签名。
    checkpoint = await saver.aget_tuple({"configurable": {"thread_id": checkpoint_key("switch")}})
    assert "private-signature" in str(checkpoint.checkpoint["channel_values"]["messages"])
