"""建立用户、会话目录与问答轮次；不修改 LangGraph 的持久化表。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_auth_conversations"
down_revision = None
branch_labels = None
depends_on = None


def timestamps():
    """为各表生成独立的创建、更新时间列，避免复用 Column 实例。"""
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    ]


def upgrade():
    """建立首版业务结构、所有权外键和游标索引。"""
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("username", sa.String(32), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
        sa.CheckConstraint("role IN ('user', 'super_admin')", name="ck_users_role"),
    )
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column(
            "last_message_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        *timestamps(),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "idx_conversations_user_recent",
        "conversations",
        ["user_id", sa.text("last_message_at DESC"), sa.text("id DESC")],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "chat_turns",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("user_content", sa.Text(), nullable=False),
        sa.Column("assistant_content", sa.Text()),
        sa.Column("assistant_message_id", sa.Text()),
        sa.Column(
            "public_events", postgresql.JSONB(), nullable=False, server_default="[]"
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("error_code", sa.Integer()),
        *timestamps(),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "conversation_id", "seq", name="uq_chat_turns_conversation_seq"
        ),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed', 'interrupted')",
            name="ck_chat_turns_status",
        ),
    )


def downgrade():
    """按外键依赖倒序移除业务表；不会触碰 checkpoint，执行会删除业务数据。"""
    op.drop_table("chat_turns")
    op.drop_index("idx_conversations_user_recent", table_name="conversations")
    op.drop_table("conversations")
    op.drop_table("users")
