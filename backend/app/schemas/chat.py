"""聊天请求及 SSE 事件的数据模型，由 API 层添加通用响应外壳。"""

from typing import ClassVar, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator
from app.schemas.model_selection import ModelIdentity, ModelSelection


class ChatRequest(BaseModel):
    """一轮聊天输入；缺省业务会话 ID 自动创建，已有 ID 由服务校验归属及删除状态。"""

    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1)
    conversation_id: UUID | None = None
    model_selection: ModelSelection | None = None
    model_selection_version: int | None = Field(default=None, gt=0, strict=True)

    @model_validator(mode="after")
    def require_selection_context(self):
        """区分首轮选择和续聊版本，已有会话必须通过独立接口切换选择。"""
        if self.conversation_id is not None and self.model_selection is not None:
            raise ValueError("已有会话请通过选择接口切换模型")
        if self.conversation_id is None and "model_selection_version" in self.model_fields_set:
            raise ValueError("新会话不能提供选择版本")
        return self

    @field_validator("message")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        """拒绝纯空白正文，合法值原样返回以保留用户输入的实际内容。

        Field 的长度约束处理空字符串，本校验补足空格、换行等情况；
        失败抛出的 ValueError 会被 Pydantic 汇总为请求校验错误。
        """
        if not value.strip():
            raise ValueError("字段不能仅包含空白字符")
        return value


class ChatEvent(BaseModel):
    """所有公开事件的业务会话归属，框架内部状态键不进入协议。"""

    conversation_id: str


class ChatStart(ChatEvent):
    """输入已提交；首轮由后端创建会话并签发轮次标识。"""

    event: ClassVar[str] = "start"
    turn_id: UUID
    is_new: bool
    model_selection: ModelSelection | None = None
    model_selection_version: int = 1
    model: ModelIdentity | None = None


class ChatDelta(ChatEvent):
    """助手的一段可见文本；message_id 区分工具调用前后的模型消息。"""

    event: ClassVar[str] = "delta"
    message_id: str
    text: str


class ChatToolCall(ChatEvent):
    """模型已生成的完整工具请求；此事件不表示工具已经开始执行。"""

    event: ClassVar[str] = "tool_call"
    message_id: str
    tool_call_id: str
    name: str
    arguments: dict[str, JsonValue]


class ChatToolStart(ChatEvent):
    """一次实际工具执行；kind 由工具 display_kind 元数据声明，不按名称猜测。"""

    event: ClassVar[str] = "tool_start"
    tool_call_id: str
    run_id: str
    name: str
    kind: Literal["tool", "command"] = "tool"
    arguments: dict[str, JsonValue] | str


class ChatToolEnd(ChatEvent):
    """一次成功执行的公开输出；只包含工具正文，不包含 artifact 或框架对象。"""

    event: ClassVar[str] = "tool_end"
    tool_call_id: str
    run_id: str
    name: str
    kind: Literal["tool", "command"] = "tool"
    output: JsonValue


class ChatToolError(ChatEvent):
    """工具调用失败的安全说明；执行前被拒绝时 run_id 为空，不终止整轮对话。"""

    event: ClassVar[str] = "tool_error"
    tool_call_id: str
    run_id: str | None = None
    name: str
    kind: Literal["tool", "command"] = "tool"
    message: str


class ChatResponse(ChatEvent):
    """本轮最终助手消息；reply 是权威完整回答，可能不同于所有增量的拼接。"""

    event: ClassVar[str] = "done"
    reply: str
    message_id: str


# event 是类级别的协议名称，不重复写入 data；所有流事件的外壳仍由路由构建。
type ChatAgentEvent = (
    ChatDelta | ChatToolCall | ChatToolStart
    | ChatToolEnd | ChatToolError | ChatResponse
)
