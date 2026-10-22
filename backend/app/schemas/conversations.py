"""会话目录及历史读取的公开结构；游标用于继续读取更早记录，不提供页码或总数。"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConversationInfo(BaseModel):
    """用户可见的会话目录条目，ORM 主键仅在响应中命名为 conversation_id。"""

    model_config = ConfigDict(from_attributes=True)
    conversation_id: UUID = Field(validation_alias="id")
    title: str
    created_at: datetime
    last_message_at: datetime


class ConversationList(BaseModel):
    """最近会话的一批结果；next_cursor 为空表示当前已无更早记录。"""

    items: list[ConversationInfo]
    next_cursor: str | None


class TurnInfo(BaseModel):
    """一轮用户输入、最终回答及公开过程快照，不包含模型内部状态。"""

    model_config = ConfigDict(from_attributes=True)
    turn_id: UUID = Field(validation_alias="id")
    seq: int
    user_content: str
    assistant_content: str | None
    assistant_message_id: str | None
    public_events: list[dict[str, Any]]
    status: Literal["running", "completed", "failed", "interrupted"]
    error_code: int | None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None


class ConversationContent(BaseModel):
    """会话元数据及最近的一批轮次，items 按轮次正序返回以便直接展示。"""

    conversation: ConversationInfo
    items: list[TurnInfo]
    next_cursor: str | None
