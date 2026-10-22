"""根据业务配置创建支持思考流和工具调用历史回传的 DeepSeek 模型客户端。

模型参数在此集中装配；实际聊天请求由 Agent 调用时发起。
"""

from typing import Any

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage
from langchain_deepseek import ChatDeepSeek

from app.core.settings import Settings


class DeepSeekChatModel(ChatDeepSeek):
    """补足当前 ChatDeepSeek 对 assistant.reasoning_content 请求回传的支持。

    官方适配负责解析流中的 reasoning_content；本类只扩展请求序列化，
    让持久化消息中的思考字段在工具后续步骤和多轮请求中原样回传。
    """

    def _get_request_payload(
        self, input_: LanguageModelInput, *, stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """生成可延续 DeepSeek 思考历史的模型请求体。

        将 input_ 转换为消息，调用父类完成请求序列化，再把已保存的助手
        reasoning_content 回填到对应请求消息；不修改图中的原始对象。
        旧 checkpoint 或非思考消息没有此字段时发送空字符串，明确表示
        没有已保存的思考，不能恢复先前已丢弃的内容。保留父类的工具、
        端点及内容序列化规则，仅处理与原消息一一对应的 assistant 字段。
        """
        messages = self._convert_input(input_).to_messages()
        payload = super()._get_request_payload(messages, stop=stop, **kwargs)
        for original, encoded in zip(messages, payload["messages"], strict=True):
            if isinstance(original, AIMessage):
                reasoning = original.additional_kwargs.get("reasoning_content")
                encoded["reasoning_content"] = reasoning if isinstance(reasoning, str) else ""
        return payload


def create_model(settings: Settings) -> DeepSeekChatModel:
    """创建供 Agent 调用的 DeepSeek 模型客户端。

    从 settings 装配模型名、密钥和服务地址，显式开启思考模式；返回的
    客户端补充历史思考字段回传，但不在这里决定哪些字段对外展示。
    仅创建客户端，不主动发送消息。调用方可将此客户端注入 Agent 工厂，
    单元测试则可注入本地模型替身，避免真实网络请求。
    """
    return DeepSeekChatModel(
        model=settings.model_name,
        api_key=settings.deepseek_api_key,
        base_url=settings.model_base_url,
        extra_body={"thinking": {"type": "enabled"}},
    )
