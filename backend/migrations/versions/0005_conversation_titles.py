"""为会话增加标题来源，保留全部存量标题并阻止自动覆盖历史数据。"""

import sqlalchemy as sa
from alembic import op

revision = "0005_conversation_titles"
down_revision = "0004_model_selection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """为旧会话设置受保护来源，新会话由业务代码显式写入 provisional。"""
    op.add_column("conversations", sa.Column("title_source", sa.String(20), nullable=False, server_default="manual"))
    op.create_check_constraint("ck_conversations_title_source", "conversations", "title_source IN ('provisional', 'auto', 'manual')")


def downgrade() -> None:
    """移除来源约束和字段，保留用户当前标题及全部聊天记录。"""
    op.drop_constraint("ck_conversations_title_source", "conversations", type_="check")
    op.drop_column("conversations", "title_source")
