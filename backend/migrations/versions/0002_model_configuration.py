"""新增全局模型配置及轮次快照，保留已有历史与 LangGraph checkpoint。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002_model_configuration"
down_revision = "0001_auth_conversations"
branch_labels = None
depends_on = None


def timestamps():
    """为配置实体创建独立的数据库时间列。"""
    return [sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())]


def upgrade():
    """建立连接与模型配置外键，初始化空默认并给旧轮次添加可空快照。"""
    op.create_table("model_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("api_format", sa.String(30), nullable=False),
        sa.Column("endpoint_config", JSONB(), nullable=False),
        sa.Column("api_key_ciphertext", sa.Text(), nullable=False),
        sa.Column("credential_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *timestamps(),
        sa.CheckConstraint("provider IN ('openai', 'anthropic', 'deepseek', 'bailian')", name="ck_model_connections_provider"),
        sa.CheckConstraint("(provider = 'openai' AND api_format IN ('responses', 'chat_completions')) OR (provider = 'anthropic' AND api_format = 'messages') OR (provider IN ('deepseek', 'bailian') AND api_format = 'chat_completions')", name="ck_model_connections_format"),
        sa.CheckConstraint("version > 0 AND credential_revision > 0", name="ck_model_connections_versions"),
        sa.CheckConstraint("jsonb_typeof(endpoint_config) = 'object'", name="ck_model_connections_endpoint"))
    op.create_table("model_configurations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("connection_id", sa.Uuid(), sa.ForeignKey("model_connections.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("catalog_model_id", sa.String(160), nullable=False),
        sa.Column("reasoning", JSONB(), nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False, server_default="16384"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        *timestamps(),
        sa.CheckConstraint("version > 0 AND max_output_tokens > 0", name="ck_model_configurations_limits"),
        sa.CheckConstraint("jsonb_typeof(reasoning) = 'object'", name="ck_model_configurations_reasoning"))
    op.create_index("ix_model_configurations_connection_id", "model_configurations", ["connection_id"])
    settings = op.create_table("chat_model_settings",
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column("model_configuration_id", sa.Uuid(), sa.ForeignKey("model_configurations.id", ondelete="RESTRICT")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("id = 1", name="ck_chat_model_settings_singleton"),
        sa.CheckConstraint("version > 0", name="ck_chat_model_settings_version"))
    op.bulk_insert(settings, [{"id": 1}])
    op.add_column("chat_turns", sa.Column("model_snapshot", JSONB(), nullable=True))


def downgrade():
    """按引用顺序撤销模型配置结构，已有公开问答历史仍保留。"""
    op.drop_column("chat_turns", "model_snapshot")
    op.drop_table("chat_model_settings")
    op.drop_index("ix_model_configurations_connection_id", table_name="model_configurations")
    op.drop_table("model_configurations")
    op.drop_table("model_connections")
