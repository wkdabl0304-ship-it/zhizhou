"""聊天请求及 SSE 事件的数据模型，由 API 层添加通用响应外壳。"""

from typing import ClassVar, Literal

from pydantic import BaseModel, Field, JsonValue, field_validator


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

    event: ClassVar[str] = "start"
    thread_id: str


class ChatDelta(ChatStart):
    """助手的一段可见文本；message_id 区分工具调用前后的模型消息。"""

    event: ClassVar[str] = "delta"
    message_id: str
    text: str


class ChatToolCall(ChatStart):
    """模型已生成的完整工具请求；此事件不表示工具已经开始执行。"""

    event: ClassVar[str] = "tool_call"
    message_id: str
    tool_call_id: str
    name: str
    arguments: dict[str, JsonValue]


class ChatToolStart(ChatStart):
    """一次实际工具执行；kind 由工具 display_kind 元数据声明，不按名称猜测。"""

    event: ClassVar[str] = "tool_start"
    tool_call_id: str
    run_id: str
    name: str
    kind: Literal["tool", "command"] = "tool"
    arguments: dict[str, JsonValue] | str


class ChatToolEnd(ChatStart):
    """一次成功执行的公开输出；只包含工具正文，不包含 artifact 或框架对象。"""

    event: ClassVar[str] = "tool_end"
    tool_call_id: str
    run_id: str
    name: str
    kind: Literal["tool", "command"] = "tool"
    output: JsonValue


class ChatToolError(ChatStart):
    """工具调用失败的安全说明；执行前被拒绝时 run_id 为空，不终止整轮对话。"""

    event: ClassVar[str] = "tool_error"
    tool_call_id: str
    run_id: str | None = None
    name: str
    kind: Literal["tool", "command"] = "tool"
    message: str


class ChatResponse(ChatStart):
    """本轮最终助手消息；reply 是权威完整回答，可能不同于所有增量的拼接。"""

    event: ClassVar[str] = "done"
    reply: str
    message_id: str


# event 是类级别的协议名称，不重复写入 data；所有流事件的外壳仍由路由构建。
type ChatAgentEvent = (
    ChatDelta | ChatToolCall | ChatToolStart
    | ChatToolEnd | ChatToolError | ChatResponse
)
