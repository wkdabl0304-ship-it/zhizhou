"""增加连接和方案启停、受限推理策略及会话选择，保留已有凭据和轮次快照。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004_model_selection"
down_revision = "0003_provider_configuration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """为存量配置设置兼容默认值，旧会话在下次有效发送时初始化选择。"""
    op.add_column("provider_configurations", sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("model_configurations", sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("model_configurations", sa.Column("reasoning_policy", JSONB(), nullable=False, server_default=sa.text("'{\"mode\":\"fixed\"}'::jsonb")))
    op.create_check_constraint("ck_model_configurations_reasoning_policy", "model_configurations", "jsonb_typeof(reasoning_policy) = 'object' AND coalesce(reasoning_policy ->> 'mode' IN ('fixed', 'selectable'), false)")
    op.add_column("conversations", sa.Column("model_selection", JSONB(none_as_null=True), nullable=True))
    op.add_column("conversations", sa.Column("model_selection_version", sa.Integer(), nullable=False, server_default="1"))
    op.create_check_constraint("ck_conversations_model_selection_version", "conversations", "model_selection_version > 0")
    op.create_check_constraint("ck_conversations_model_selection", "conversations", "model_selection IS NULL OR jsonb_typeof(model_selection) = 'object'")


def downgrade() -> None:
    """移除本次新增字段和约束，不改写原推理值、默认引用或历史快照。"""
    op.drop_constraint("ck_conversations_model_selection", "conversations", type_="check")
    op.drop_constraint("ck_conversations_model_selection_version", "conversations", type_="check")
    op.drop_column("conversations", "model_selection_version")
    op.drop_column("conversations", "model_selection")
    op.drop_constraint("ck_model_configurations_reasoning_policy", "model_configurations", type_="check")
    op.drop_column("model_configurations", "reasoning_policy")
    op.drop_column("model_configurations", "enabled")
    op.drop_column("provider_configurations", "enabled")
