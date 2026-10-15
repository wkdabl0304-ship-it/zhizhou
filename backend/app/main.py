"""定义知舟 FastAPI 应用、生命周期和聊天接口。

Web 进程由包入口启动；本模块负责启动时组装资源、退出时释放资源，
并将 HTTP 请求交给 Agent。错误响应统一交由 API 异常处理器转换。
"""

import logging
from collections.abc import AsyncIterator
from contextlib import ExitStack, asynccontextmanager

from fastapi import FastAPI, Request

from app.agents.agent import ChatAgent
from app.agents.factory import build_agent
from app.agents.models import create_model
from app.agents.tools.weather import get_weather
from app.api.exception_handlers import ERROR_RESPONSES, register_exception_handlers
from app.config.logging import configure_logging
from app.config.settings import load_logging_settings, load_settings
from app.db.checkpoint import open_checkpointer
from app.errors.codes import ErrorCode
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.response import ApiResponse, failure, success

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """管理应用从启动到关闭期间共享的 Agent 和数据库连接。

    Args:
        app: 当前 FastAPI 实例，初始化后的 Agent 存放在 app.state 中。

    Yields:
        None: yield 前完成启动，yield 后执行退出清理。

    Raises:
        Exception: 配置、模型或数据库初始化失败时记录原始异常并终止启动。
    """
    configure_logging(load_logging_settings()) # 这里再次配置日志是为了兼容用 uvicorn 启动项目
    # ExitStack 管理资源，确保资源被正确释放
    with ExitStack() as resources:
        try:
            settings = load_settings()
            model = create_model(settings)
            checkpointer = resources.enter_context(open_checkpointer(settings))
            app.state.chat_agent = ChatAgent(build_agent(model, [get_weather], checkpointer))
        except Exception:
            logger.exception("应用启动失败")
            raise
        # 只有所有资源均准备就绪，才开始接受业务请求。
        logger.info("应用启动完成")
        try:
            yield
        finally:
            # 先撤销对外暴露的对象，再关闭其依赖，防止继续使用已关闭连接。
            del app.state.chat_agent
            resources.close()
            logger.info("应用资源已关闭")


app = FastAPI(title="知舟聊天 API", lifespan=lifespan, responses=ERROR_RESPONSES) # responses 让 Swagger 显示错误响应
# 注册异常类型到响应的映射，后续路由不需要各自处理相同异常。
register_exception_handlers(app)


@app.post(
    "/chat",
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
def chat(body: ChatRequest, request: Request) -> ApiResponse[ChatResponse]:
    """发送一轮消息，并在成功时返回统一格式的助手回复。

    body 由 Pydantic 校验；thread_id 用来读取和续写同一段历史。
    request 用于取得应用启动时创建的 Agent。业务异常和系统异常继续
    向外传播，分别由全局处理器转换为约定的 HTTP 状态与数字 code。
    """
    reply = request.app.state.chat_agent.chat(body.message, body.thread_id)
    return success(ChatResponse(reply=reply, thread_id=body.thread_id))
