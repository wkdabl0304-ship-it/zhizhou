import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from app.agents.agent import ChatAgent
from app.agents.factory import build_agent
from app.agents.models import create_model
from app.agents.tools.weather import get_weather
from app.config.settings import load_settings
from app.db.checkpoint import open_checkpointer
from app.schemas.chat import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = load_settings()
    model = create_model(settings)
    with open_checkpointer(settings) as checkpointer:
        app.state.chat_agent = ChatAgent(build_agent(model, [get_weather], checkpointer))
        try:
            yield
        finally:
            del app.state.chat_agent


app = FastAPI(title="知舟聊天 API", lifespan=lifespan)


@app.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, request: Request) -> ChatResponse:
    try:
        reply = request.app.state.chat_agent.chat(body.message, body.thread_id)
    except Exception:
        logger.exception("Agent 对话执行失败")
        raise HTTPException(status_code=500, detail="对话执行失败，请稍后重试") from None
    return ChatResponse(reply=reply, thread_id=body.thread_id)
