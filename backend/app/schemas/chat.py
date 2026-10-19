"""聊天请求及 SSE 事件的数据模型，由 API 层添加通用响应外壳。"""

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    """一轮聊天输入；message 是用户消息，thread_id 用于关联持久化历史。"""

    message: str = Field(min_length=1)
    thread_id: str = Field(min_length=1)

    @field_validator("message", "thread_id")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        """拒绝纯空白字符串，合法值原样返回以保留消息及标识的实际内容。

        Field 的长度约束处理空字符串，本校验补足空格、换行等情况；
        失败抛出的 ValueError 会被 Pydantic 汇总为请求校验错误。
        """
        if not value.strip():
            raise ValueError("字段不能仅包含空白字符")
        return value


class ChatStart(BaseModel):
    """请求已接受；thread_id 对应排队或执行中的会话。"""

    thread_id: str


class ChatDelta(ChatStart):
    """助手的一段可见文本；message_id 区分工具调用前后的模型消息。"""

    message_id: str
    text: str


class ChatResponse(ChatStart):
    """本轮最终助手消息；reply 是权威完整回答，可能不同于所有增量的拼接。"""

    reply: str
    message_id: str
