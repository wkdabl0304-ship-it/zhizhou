"""聊天 SSE 子路由：编码正文、思考与工具过程，并在流内报告生成失败。

资源由生命周期创建并注入；参数与框架错误仍由全局 JSON 处理器负责。
流一旦建立，HTTP 状态不可修改，Agent 异常必须转换成终止 error 事件。
"""

import logging
from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import Annotated

from fastapi import APIRouter, Depends

from app.agents.agent import ChatAgent
from app.api.dependencies import get_chat_agent
from app.api.streaming import DisconnectStreamingResponse, encode_event
from app.errors.codes import ErrorCode
from app.errors.exceptions import AppError, ServiceError, log_app_error
from app.schemas.chat import (
    ChatDelta, ChatReasoningDelta, ChatRequest, ChatResponse, ChatStart,
    ChatToolCall, ChatToolEnd, ChatToolError, ChatToolStart,
)
from app.schemas.response import failure, success

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["聊天"])

# 用真实序列化函数维护文档示例，避免协议样例与运行时编码各自演变。
_EXAMPLE = "".join([
    encode_event("start", success(ChatStart(thread_id="conversation-001"))),
    encode_event("reasoning_delta", success(ChatReasoningDelta(thread_id="conversation-001", message_id="plan-1", text="需要查询天气。"))),
    encode_event("tool_call", success(ChatToolCall(thread_id="conversation-001", message_id="plan-1", tool_call_id="weather-1", name="get_weather", arguments={"city": "上海"}))),
    encode_event("tool_start", success(ChatToolStart(thread_id="conversation-001", tool_call_id="weather-1", run_id="run-1", name="get_weather", arguments={"city": "上海"}))),
    encode_event("tool_end", success(ChatToolEnd(thread_id="conversation-001", tool_call_id="weather-1", run_id="run-1", name="get_weather", output="上海今天晴天，温度 25°C"))),
    encode_event("delta", success(ChatDelta(thread_id="conversation-001", message_id="reply-1", text="你好"))),
    encode_event("done", success(ChatResponse(thread_id="conversation-001", message_id="reply-1", reply="你好"))),
])


@router.post(
    "",
    response_class=DisconnectStreamingResponse,
    response_model=None,
    responses={
        200: {
            "description": (
                "SSE：start 表示接受请求；delta 按 message_id 输出 text；done 包含最终 reply。"
                "成功事件 code=0；error 使用非零错误码且 data=null，之后不再发送 done。"
                "delta 可能包含工具调用前的助手文字，done.reply 是最终完整回答。"
                "reasoning_delta 输出模型实际提供的思考文本，不保证每个模型都有。"
                "tool_call 表示模型已生成完整调用；tool_start/tool_end/tool_error 表示实际执行状态，"
                "按 tool_call_id 关联，run_id 区分每次执行。kind=command 表示已注册的命令工具。"
                "tool_error 不是整轮终止事件；error 才终止本轮。连接断开会取消生成，不保证终止事件。"
            ),
            "content": {"text/event-stream": {
                "schema": {"type": "string"},
                "examples": {
                    "success": {"value": _EXAMPLE},
                    "tool_error": {"value": encode_event("tool_error", success(ChatToolError(
                        thread_id="conversation-001", tool_call_id="weather-1", run_id="run-1",
                        name="get_weather", message=ErrorCode.TOOL_FAILED.message,
                    )))},
                    "error": {"value": encode_event("error", failure(ErrorCode.CHAT_FAILED))},
                },
            }},
        },
    },
)
async def chat(
    body: ChatRequest,
    chat_agent: Annotated[ChatAgent, Depends(get_chat_agent)],
) -> DisconnectStreamingResponse:
    """接受一轮消息并立即开始 SSE；底层图仅由响应迭代器执行一次。

    start 在取得会话锁前发送。调用方须逐事件检查 code 并以 done/error
    判断本轮结束；客户端断开后关闭图，已写入的 checkpoint 不回滚。
    """
    async def events() -> AsyncIterator[str]:
        """编码数据及终止事件，关闭底层异步流并保留取消异常的传播。"""
        yield encode_event("start", success(ChatStart(thread_id=body.thread_id)))
        try:
            async with aclosing(chat_agent.astream(body.message, body.thread_id)) as stream:
                async for event in stream:
                    yield encode_event(event.event, success(event))
        except AppError as exc:
            log_app_error(logger, exc, context={"thread_id": body.thread_id})
            yield encode_event("error", failure(exc.error_code))
        except Exception as exc:
            # 依赖替身或编码异常也不能在已发送响应头后退回 JSON 错误响应。
            error = ServiceError(ErrorCode.CHAT_FAILED)
            log_app_error(logger, error, context={"thread_id": body.thread_id}, cause=exc)
            yield encode_event("error", failure(error.error_code))

    return DisconnectStreamingResponse(
        events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
