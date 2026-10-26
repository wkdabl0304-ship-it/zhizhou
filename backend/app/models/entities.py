"""用户与会话模块的 SQLAlchemy 实体；只映射业务表，不接管 LangGraph 内部表。"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """业务 ORM 元数据入口，Alembic 仅使用这里的表集合。"""


class User(Base):
    """登录账号；角色暂不改变会话所有权约束，密码只保存带盐摘要。"""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'super_admin')", name="ck_users_role"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(32), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default="user", server_default="user")
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Conversation(Base):
    """业务会话及软删除状态；ID 由后端生成，与用户归属一起作为访问边界。"""

    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint("model_selection_version > 0", name="ck_conversations_model_selection_version"),
        CheckConstraint("model_selection IS NULL OR jsonb_typeof(model_selection) = 'object'", name="ck_conversations_model_selection"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(100))
    # 选择允许随配置删除而失效，JSON 内的方案引用不建立外键，也不级联修改历史。
    model_selection: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    model_selection_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# 部分索引只覆盖可见会话；排序的 UUID 次键消除同时间记录的歧义。
Index(
    "idx_conversations_user_recent",
    Conversation.user_id,
    Conversation.last_message_at.desc(),
    Conversation.id.desc(),
    postgresql_where=Conversation.deleted_at.is_(None),
)


class ChatTurn(Base):
    """一轮输入及其公开执行快照；JSONB 不保存内部推理或原始异常。"""

    __tablename__ = "chat_turns"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id", "seq", name="uq_chat_turns_conversation_seq"
        ),
        CheckConstraint(
            "status IN ('running', 'completed', 'failed', 'interrupted')",
            name="ck_chat_turns_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id"))
    seq: Mapped[int] = mapped_column(BigInteger)
    user_content: Mapped[str] = mapped_column(Text)
    assistant_content: Mapped[str | None] = mapped_column(Text)
    assistant_message_id: Mapped[str | None] = mapped_column(Text)
    public_events: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="running", server_default="running"
    )
    error_code: Mapped[int | None] = mapped_column(Integer)
    # 只记录实际模型与无密钥参数，旧轮次保持空值，不推测历史配置。
    model_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
