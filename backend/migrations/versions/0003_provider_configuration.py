"""将模型供应商接入配置统一命名为供应商配置，保留现有凭据、引用和轮次快照。"""

from alembic import op

revision = "0003_provider_configuration"
down_revision = "0002_model_configuration"
branch_labels = None
depends_on = None


def rename_configuration(old_table: str, new_table: str, old_column: str, new_column: str) -> None:
    """重命名供应商配置表及关联结构，不重建数据，也不改变引用和版本。

    参数仅来自本迁移内的固定标识符；双向迁移共用同一流程，保持约束名与 ORM 一致。
    """
    op.rename_table(old_table, new_table)
    op.alter_column("model_configurations", old_column, new_column_name=new_column)
    for suffix in ("pkey", "provider", "format", "versions", "endpoint"):
        prefix = "" if suffix == "pkey" else "ck_"
        op.execute(f'ALTER TABLE {new_table} RENAME CONSTRAINT {prefix}{old_table}_{suffix} TO {prefix}{new_table}_{suffix}')
    op.execute(f'ALTER TABLE model_configurations RENAME CONSTRAINT model_configurations_{old_column}_fkey TO model_configurations_{new_column}_fkey')
    op.execute(f'ALTER INDEX ix_model_configurations_{old_column} RENAME TO ix_model_configurations_{new_column}')


def rename_snapshot_fields(old_id: str, new_id: str, old_version: str, new_version: str) -> None:
    """更新旧轮次快照的字段名称，保留参数、其他字段及原本为空的历史快照。"""
    # 按字段是否存在分别转换，避免为不含该字段的历史快照补造 null 值。
    for old, new in ((old_id, new_id), (old_version, new_version)):
        op.execute(f"""
            UPDATE chat_turns
            SET model_snapshot = (model_snapshot - '{old}')
                || jsonb_build_object('{new}', model_snapshot -> '{old}')
            WHERE model_snapshot ? '{old}'
        """)


def upgrade() -> None:
    """把已部署的连接配置和轮次快照迁移为供应商配置命名。"""
    rename_configuration("model_connections", "provider_configurations", "connection_id", "provider_configuration_id")
    rename_snapshot_fields("connection_id", "provider_configuration_id", "connection_version", "provider_configuration_version")


def downgrade() -> None:
    """恢复旧版结构和快照字段，保留供应商配置及模型默认引用。"""
    rename_snapshot_fields("provider_configuration_id", "connection_id", "provider_configuration_version", "connection_version")
    rename_configuration("provider_configurations", "model_connections", "provider_configuration_id", "connection_id")
