import logging
from collections.abc import AsyncIterator
from contextlib import ExitStack, asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from app.agents.agent import ChatAgent
from app.agents.factory import build_agent
from app.agents.models import create_model
from app.agents.tools.weather import get_weather
from app.config.logging import configure_logging
from app.config.settings import load_logging_settings, load_settings
from app.db.checkpoint import open_checkpointer
from app.schemas.chat import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
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
        logger.info("应用启动完成")
        try:
            yield
        finally:
            del app.state.chat_agent
            resources.close()
            logger.info("应用资源已关闭")


app = FastAPI(title="知舟聊天 API", lifespan=lifespan)


@app.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, request: Request) -> ChatResponse:
    try:
        reply = request.app.state.chat_agent.chat(body.message, body.thread_id)
    except Exception:
        # Agent 层已记录异常，HTTP 层只负责转换响应。
        raise HTTPException(status_code=500, detail="对话执行失败，请稍后重试") from None
    return ChatResponse(reply=reply, thread_id=body.thread_id)
