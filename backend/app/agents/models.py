"""根据业务配置创建智能体使用的 DeepSeek/OpenAI 兼容模型客户端。

模型参数在此集中装配；实际聊天请求由 Agent 调用时发起。
"""

from langchain_openai import ChatOpenAI

from app.config.settings import Settings


def create_model(settings: Settings) -> ChatOpenAI:
    """使用 settings 的模型名、密钥和服务地址返回 ChatOpenAI 客户端。

    仅创建客户端，不主动发送消息。调用方可将此客户端注入 Agent 工厂，
    单元测试则可注入本地模型替身，避免真实网络请求。
    """
    return ChatOpenAI(
        model=settings.model_name,
        api_key=settings.deepseek_api_key,
        base_url=settings.model_base_url,
    )
