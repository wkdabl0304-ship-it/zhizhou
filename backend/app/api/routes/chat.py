"""聊天 SSE 子路由：编码进度正文与工具过程，并在流内报告生成失败。

资源由生命周期创建并注入；参数与框架错误仍由全局 JSON 处理器负责。
流一旦建立，HTTP 状态不可修改，Agent 异常必须转换成终止 error 事件。
"""

import logging
from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import Annotated

from fastapi import APIRouter, Depends

from app.llm.runtime import ConfiguredChatAgent
from app.api.dependencies import (
    get_chat_agent,
    get_conversation_service,
    get_current_user,
)
from app.api.streaming import DisconnectStreamingResponse, encode_event
from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import AppError, ServiceError, log_app_error
from app.models import User
from app.schemas.chat import (
    ChatDelta,
    ChatRequest,
    ChatResponse,
    ChatStart,
    ChatToolCall,
    ChatToolEnd,
    ChatToolError,
    ChatToolStart,
)
from app.schemas.response import failure, success
from app.services.conversations import ConversationService, PreparedChat

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["聊天"])

# 用真实序列化函数维护文档示例，避免协议样例与运行时编码各自演变。
_EXAMPLE = "".join(
    [
        encode_event(
            "start",
            success(
                ChatStart(
                    conversation_id="00000000-0000-4000-8000-000000000001",
                    turn_id="00000000-0000-4000-8000-000000000001",
                    is_new=True,
                )
            ),
        ),
        encode_event(
            "delta",
            success(
                ChatDelta(
                    conversation_id="00000000-0000-4000-8000-000000000001",
                    message_id="plan-1",
                    text="我先查询上海的天气。",
                )
            ),
        ),
        encode_event(
            "tool_call",
            success(
                ChatToolCall(
                    conversation_id="00000000-0000-4000-8000-000000000001",
                    message_id="plan-1",
                    tool_call_id="weather-1",
                    name="get_weather",
                    arguments={"city": "上海"},
                )
            ),
        ),
        encode_event(
            "tool_start",
            success(
                ChatToolStart(
                    conversation_id="00000000-0000-4000-8000-000000000001",
                    tool_call_id="weather-1",
                    run_id="run-1",
                    name="get_weather",
                    arguments={"city": "上海"},
                )
            ),
        ),
        encode_event(
            "tool_end",
            success(
                ChatToolEnd(
                    conversation_id="00000000-0000-4000-8000-000000000001",
                    tool_call_id="weather-1",
                    run_id="run-1",
                    name="get_weather",
                    output="上海今天晴天，温度 25°C",
                )
            ),
        ),
        encode_event(
            "delta",
            success(
                ChatDelta(
                    conversation_id="00000000-0000-4000-8000-000000000001",
                    message_id="reply-1",
                    text="你好",
                )
            ),
        ),
        encode_event(
            "done",
            success(
                ChatResponse(
                    conversation_id="00000000-0000-4000-8000-000000000001",
                    message_id="reply-1",
                    reply="你好",
                )
            ),
        ),
    ]
)


async def prepare_chat(
    body: ChatRequest,
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ConversationService, Depends(get_conversation_service)],
) -> AsyncIterator[PreparedChat]:
    """为聊天接口准备已经落库的输入和持锁执行上下文。

    使用已认证的 user 与校验后的 body 调用会话服务，yield PreparedChat
    给路由。依赖采用 request scope，使上下文在 SSE 结束后才退出并释放锁；
    归属或执行冲突在响应建立前返回普通 JSON 错误。
    """
    async with service.prepare(user.id, body.message, body.conversation_id) as prepared:
        yield prepared


@router.post(
    "",
    response_class=DisconnectStreamingResponse,
    response_model=None,
    responses={
        200: {
            "description": (
                "SSE：start 返回后端生成的 conversation_id、turn_id 和 is_new；delta 按 message_id 输出 text；done 包含最终 reply。"
                "成功事件 code=0；error 使用非零错误码且 data=null，之后不再发送 done。"
                "delta 可能包含工具调用前的助手文字，done.reply 是最终完整回答。"
                "工具调用前通过 delta 输出行动说明，不对外返回模型推理。"
                "tool_call 表示模型已生成完整调用；tool_start/tool_end/tool_error 表示实际执行状态，"
                "按 tool_call_id 关联，run_id 区分每次执行。kind=command 表示已注册的命令工具。"
                "tool_error 不是整轮终止事件；error 才终止本轮。连接断开会取消生成，不保证终止事件。"
            ),
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                    "examples": {
                        "success": {"value": _EXAMPLE},
                        "tool_error": {
                            "value": encode_event(
                                "tool_error",
                                success(
                                    ChatToolError(
                                        conversation_id="00000000-0000-4000-8000-000000000001",
                                        tool_call_id="weather-1",
                                        run_id="run-1",
                                        name="get_weather",
                                        message=ErrorCode.TOOL_FAILED.message,
                                    )
                                ),
                            )
                        },
                        "error": {
                            "value": encode_event(
                                "error", failure(ErrorCode.CHAT_FAILED)
                            )
                        },
                    },
                }
            },
        },
    },
)
async def chat(
    prepared: Annotated[PreparedChat, Depends(prepare_chat, scope="request")],
    chat_agent: Annotated[ConfiguredChatAgent, Depends(get_chat_agent)],
    service: Annotated[ConversationService, Depends(get_conversation_service)],
) -> DisconnectStreamingResponse:
    # 接口用途：将已准备好的本轮聊天作为 SSE 响应交给浏览器，持续传输进度和最终回答。
    # 下方文档字符串会进入 OpenAPI，阅读补充使用普通注释，保持对外接口描述不变。
    """已提交输入后建立 SSE；身份、会话归属和执行冲突均在响应头发送前校验。

    底层图仅执行一次，业务最终结果提交后才发送 done；客户端断开会关闭图，
    尽力保存公开过程并释放请求级执行锁，不回滚已有 checkpoint。
    """

    async def events() -> AsyncIterator[str]:
        """把会话服务事件转换为浏览器可读取的 SSE 文本流。

        正常事件用 success 包装，应用异常或未知故障转换为终止 error 事件；
        离开迭代时关闭服务流，取消异常继续传播以触发外层清理。
        """
        try:
            async with aclosing(service.stream(prepared, chat_agent)) as stream:
                async for event in stream:
                    yield encode_event(event.event, success(event))
        except AppError as exc:
            log_app_error(
                logger, exc, context={"conversation_id": str(prepared.conversation_id)}
            )
            yield encode_event("error", failure(exc.error_code))
        except Exception as exc:  # noqa: BLE001 — SSE 响应头已发送，编码或依赖故障必须转换为终止事件。
            # 依赖替身或编码异常也不能在已发送响应头后退回 JSON 错误响应。
            error = ServiceError(ErrorCode.CHAT_FAILED)
            log_app_error(
                logger,
                error,
                context={"conversation_id": str(prepared.conversation_id)},
                cause=exc,
            )
            yield encode_event("error", failure(error.error_code))

    return DisconnectStreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
