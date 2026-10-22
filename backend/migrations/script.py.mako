"""${message}；业务数据库版本迁移，不修改第三方 checkpoint 表。"""

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade():
    """应用本版本的业务结构变更。"""
    ${upgrades if upgrades else "pass"}


def downgrade():
    """撤销本版本的业务结构变更，执行前应确认数据保留要求。"""
    ${downgrades if downgrades else "pass"}
