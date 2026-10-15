"""聊天接口的输入和业务数据模型，不包含通用响应外壳。

Pydantic 在请求进入路由前执行校验；最终回复嵌入 ApiResponse.data。
"""

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


class ChatResponse(BaseModel):
    """成功时返回的业务数据：最终助手文本及原始对话标识。"""

    reply: str
    thread_id: str
