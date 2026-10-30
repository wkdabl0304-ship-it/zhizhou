"""会话标题修改、目录及历史读取的公开结构；游标用于向前读取，不提供页码或总数。"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.schemas.model_selection import ModelIdentity, ModelSelection, SelectionIssue


def normalize_title(value: str) -> str:
    """将标题中的连续空白合并为一个空格，供临时标题和正式标题共用。"""
    return " ".join(value.split())


class ConversationTitleUpdate(BaseModel):
    """接收用户标题，先规范化空白，再按 Unicode 字符数校验长度。"""

    model_config = ConfigDict(extra="forbid")
    title: str = Field(strict=True, min_length=1, max_length=100)

    @field_validator("title", mode="before")
    @classmethod
    def normalize(cls, value: object) -> object:
        """规范化字符串标题，同时保留非字符串值交给严格类型校验拒绝。"""
        return normalize_title(value) if isinstance(value, str) else value


class ConversationInfo(BaseModel):
    """用户可见的会话目录条目，ORM 主键仅在响应中命名为 conversation_id。"""

    model_config = ConfigDict(from_attributes=True)
    conversation_id: UUID = Field(validation_alias="id")
    title: str
    created_at: datetime
    last_message_at: datetime
    model_selection: ModelSelection | None = None
    model_selection_version: int = 1
    model_selection_issue: SelectionIssue | None = None


class ConversationList(BaseModel):
    """最近会话的一批结果；next_cursor 为空表示当前已无更早记录。"""

    items: list[ConversationInfo]
    next_cursor: str | None


class TurnInfo(BaseModel):
    """一轮用户输入、最终回答及公开过程快照，不包含模型内部状态。"""

    model_config = ConfigDict(from_attributes=True)
    turn_id: UUID = Field(validation_alias="id")
    seq: int
    model: ModelIdentity | None = None
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
