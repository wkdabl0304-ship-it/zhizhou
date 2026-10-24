"""DeepSeek 专用客户端补充：保留原生解析，补足历史思考字段回传。"""

from typing import Any

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage
from langchain_deepseek import ChatDeepSeek

from app.llm.providers.failures import SafeStreamMixin


class DeepSeekChatModel(SafeStreamMixin, ChatDeepSeek):
    """使用官方 LangChain 集成并补齐当前版本的 reasoning_content 请求序列化。"""

    def _get_request_payload(self, input_: LanguageModelInput, *, stop: list[str] | None = None, **kwargs: Any) -> dict[str, Any]:
        """生成可延续工具思考历史的请求，旧消息缺失字段时使用空值且不修改原对象。"""
        messages = self._convert_input(input_).to_messages()
        payload = super()._get_request_payload(messages, stop=stop, **kwargs)
        for original, encoded in zip(messages, payload["messages"], strict=True):
            if isinstance(original, AIMessage):
                reasoning = original.additional_kwargs.get("reasoning_content")
                encoded["reasoning_content"] = reasoning if isinstance(reasoning, str) else ""
        return payload
