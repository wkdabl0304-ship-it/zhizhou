"""根据业务配置创建支持思考流和工具调用历史回传的 DeepSeek 模型客户端。

模型参数在此集中装配；实际聊天请求由 Agent 调用时发起。
"""

from typing import Any

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage
from langchain_deepseek import ChatDeepSeek

from app.config.settings import Settings


class DeepSeekChatModel(ChatDeepSeek):
    """补足当前 ChatDeepSeek 对 assistant.reasoning_content 请求回传的支持。

    官方适配负责解析流中的 reasoning_content；本类只扩展请求序列化，
    让持久化消息中的思考字段在工具后续步骤和多轮请求中原样回传。
    """

    def _get_request_payload(
        self, input_: LanguageModelInput, *, stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """构建请求并回填历史助手思考，不修改图中原始消息对象。

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
    """使用 settings 返回保留 DeepSeek 思考字段的客户端，并显式启用思考模式。

    仅创建客户端，不主动发送消息。调用方可将此客户端注入 Agent 工厂，
    单元测试则可注入本地模型替身，避免真实网络请求。
    """
    return DeepSeekChatModel(
        model=settings.model_name,
        api_key=settings.deepseek_api_key,
        base_url=settings.model_base_url,
        extra_body={"thinking": {"type": "enabled"}},
    )
