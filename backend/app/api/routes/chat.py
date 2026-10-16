"""聊天业务子路由：定义消息输入、Agent 调用和统一响应文档。

本模块仅声明 /chat 业务前缀，由总路由叠加 /api。Agent 通过公共依赖
注入，应用资源的创建与释放仍由生命周期管理。
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.agents.agent import ChatAgent
from app.api.dependencies import get_chat_agent
from app.errors.codes import ErrorCode
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.response import ApiResponse, failure, success

router = APIRouter(prefix="/chat", tags=["聊天"])


@router.post(
    "",
    response_model=ApiResponse[ChatResponse],
    responses={
        200: {
            "description": "HTTP 200 包含成功和业务失败；code=0 表示业务成功，非零业务码表示业务失败。",
            "content": {
                "application/json": {
                    "examples": {
                        "success": {
                            "value": success(
                                ChatResponse(reply="你好", thread_id="conversation-001")
                            ).model_dump(mode="json"),
                        },
                        "business_error": {
                            "value": failure(ErrorCode.BUSINESS_ERROR).model_dump(mode="json"),
                        },
                    },
                },
            },
        },
    },
)
def chat(
    body: ChatRequest,
    chat_agent: Annotated[ChatAgent, Depends(get_chat_agent)],
) -> ApiResponse[ChatResponse]:
    """发送一轮消息，并在成功时返回统一格式的助手回复。

    body 由 Pydantic 校验；thread_id 用来读取和续写同一段历史。
    chat_agent 由公共依赖取得，复用应用启动时创建的实例。业务异常和
    系统异常继续向外传播，由全局处理器转换为约定的状态和数字 code。
    """
    reply = chat_agent.chat(body.message, body.thread_id)
    return success(ChatResponse(reply=reply, thread_id=body.thread_id))
