"""智能体使用的模型客户端。"""

from langchain_openai import ChatOpenAI

from app.config.settings import Settings


def create_model(settings: Settings) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.model_name,
        api_key=settings.deepseek_api_key,
        base_url=settings.model_base_url,
    )
