"""建立共享文件空间、目录树和原文件生命周期，并初始化已有账号与部门。"""

from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from alembic import op

revision = "0007_file_spaces"
down_revision = "0006_authorization"
branch_labels = None
depends_on = None

# 冻结迁移种子及约束，不引用会随业务演进的 ORM 或服务代码。
PERMISSIONS = {"file:read": "读取文件", "file:upload": "上传文件及创建目录",
               "file:update": "重命名文件及目录", "file:delete": "删除文件及目录",
               "file_upload_limit:update": "修改上传大小限制"}


def seed_id(kind: str, code: str):
    """复用权限模块的稳定种子标识，保证新增授权关联已有内置角色。"""
    return uuid5(NAMESPACE_URL, f"zhizhou:{kind}:{code}")


def upgrade() -> None:
    """创建文件结构与范围授权，为存量用户和部门补齐空空间及默认上传策略。"""
    spaces = op.create_table("file_spaces",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("department_id", sa.Uuid(), sa.ForeignKey("departments.id", ondelete="SET NULL")),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("kind IN ('global', 'department', 'personal')", name="ck_file_spaces_kind"),
        sa.CheckConstraint("(kind = 'global' AND department_id IS NULL AND owner_id IS NULL AND deleted_at IS NULL) OR "
                           "(kind = 'personal' AND department_id IS NULL AND owner_id IS NOT NULL AND deleted_at IS NULL) OR "
                           "(kind = 'department' AND owner_id IS NULL AND (department_id IS NOT NULL OR deleted_at IS NOT NULL))",
                           name="ck_file_spaces_ownership"))
    op.create_index("uq_file_spaces_global", "file_spaces", ["kind"], unique=True,
                    postgresql_where=sa.text("kind = 'global' AND deleted_at IS NULL"))
    op.create_index("uq_file_spaces_department", "file_spaces", ["department_id"], unique=True,
                    postgresql_where=sa.text("kind = 'department' AND deleted_at IS NULL"))
    op.create_index("uq_file_spaces_personal", "file_spaces", ["owner_id"], unique=True,
                    postgresql_where=sa.text("kind = 'personal' AND deleted_at IS NULL"))
    policies = op.create_table("file_upload_policies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("scope_type", sa.String(16), nullable=False),
        sa.Column("department_id", sa.Uuid(), sa.ForeignKey("departments.id", ondelete="CASCADE")),
        sa.Column("max_file_size_bytes", sa.BigInteger(), nullable=False, server_default="104857600"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("scope_type IN ('global', 'personal', 'department')", name="ck_file_upload_policies_scope"),
        sa.CheckConstraint("(scope_type = 'department' AND department_id IS NOT NULL) OR "
                           "(scope_type IN ('global', 'personal') AND department_id IS NULL)", name="ck_file_upload_policies_department"),
        sa.CheckConstraint("max_file_size_bytes BETWEEN 1 AND 1099511627776", name="ck_file_upload_policies_size"),
        sa.CheckConstraint("version > 0", name="ck_file_upload_policies_version"))
    op.create_index("uq_file_upload_policies_scope", "file_upload_policies", ["scope_type"], unique=True,
                    postgresql_where=sa.text("department_id IS NULL"))
    op.create_index("uq_file_upload_policies_department", "file_upload_policies", ["department_id"], unique=True,
                    postgresql_where=sa.text("department_id IS NOT NULL"))
    op.create_table("file_blobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("storage_key", sa.String(100), nullable=False, unique=True),
        sa.Column("state", sa.String(16), nullable=False, server_default="staging"),
        sa.Column("size_bytes", sa.BigInteger()),
        sa.Column("sha256", sa.CHAR(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("state IN ('staging', 'ready', 'delete_pending', 'purged')", name="ck_file_blobs_state"),
        sa.CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="ck_file_blobs_size"),
        sa.CheckConstraint("sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'", name="ck_file_blobs_sha256"),
        sa.CheckConstraint("state <> 'ready' OR (size_bytes IS NOT NULL AND sha256 IS NOT NULL)", name="ck_file_blobs_ready"))
    op.create_index("ix_file_blobs_state", "file_blobs", ["state"])
    op.create_table("file_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("space_id", sa.Uuid(), sa.ForeignKey("file_spaces.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("parent_id", sa.Uuid()),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_key", sa.Text(), nullable=False),
        sa.Column("blob_id", sa.Uuid(), sa.ForeignKey("file_blobs.id", ondelete="RESTRICT"), unique=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("space_id", "id", name="uq_file_entries_space_id"),
        sa.ForeignKeyConstraint(["space_id", "parent_id"], ["file_entries.space_id", "file_entries.id"],
                                name="fk_file_entries_parent", ondelete="RESTRICT"),
        sa.CheckConstraint("kind IN ('file', 'folder')", name="ck_file_entries_kind"),
        sa.CheckConstraint("(kind = 'file' AND blob_id IS NOT NULL) OR (kind = 'folder' AND blob_id IS NULL)", name="ck_file_entries_blob"),
        sa.CheckConstraint("length(name) BETWEEN 1 AND 255 AND name = btrim(name)", name="ck_file_entries_name"),
        sa.CheckConstraint("version > 0", name="ck_file_entries_version"),
        sa.CheckConstraint("parent_id IS NULL OR parent_id <> id", name="ck_file_entries_parent"))
    op.create_index("uq_file_entries_name", "file_entries", ["space_id", "parent_id", "name_key"], unique=True,
                    postgresql_nulls_not_distinct=True, postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_index("idx_file_entries_directory", "file_entries", ["space_id", "parent_id", sa.text("created_at DESC"), sa.text("id DESC")],
                    postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_index("idx_file_entries_parent", "file_entries", ["space_id", "parent_id"])
    op.bulk_insert(spaces, [{"id": uuid4(), "kind": "global"}])
    op.bulk_insert(policies, [{"id": uuid4(), "scope_type": scope} for scope in ("global", "personal")])
    connection = op.get_bind()
    # MD5 仅用于一次性数据回填的 UUID，不承担安全摘要职责。
    connection.execute(sa.text("""INSERT INTO file_spaces(id,kind,owner_id)
        SELECT md5('personal-space:' || id::text)::uuid,'personal',id FROM users"""))
    connection.execute(sa.text("""INSERT INTO file_spaces(id,kind,department_id)
        SELECT md5('department-space:' || id::text)::uuid,'department',id FROM departments"""))
    connection.execute(sa.text("""INSERT INTO file_upload_policies(id,scope_type,department_id)
        SELECT md5('department-policy:' || id::text)::uuid,'department',id FROM departments"""))
    permission_table = sa.table("permissions", sa.column("id", sa.Uuid()), sa.column("code"), sa.column("name"))
    op.bulk_insert(permission_table, [{"id": seed_id("permission", code), "code": code, "name": name}
                                      for code, name in PERMISSIONS.items()])
    grant_table = sa.table("role_permissions", sa.column("role_id", sa.Uuid()),
                          sa.column("permission_id", sa.Uuid()), sa.column("scope_type"))
    grants = []
    for code in PERMISSIONS:
        grants.extend([{"role_id": seed_id("role", role), "permission_id": seed_id("permission", code), "scope_type": scope}
                       for role, scope in (("super_admin", "global"), ("department_admin", "department"))])
        if code.startswith("file:"):
            grants.append({"role_id": seed_id("role", "user"), "permission_id": seed_id("permission", code), "scope_type": "self"})
    op.bulk_insert(grant_table, grants)


def downgrade() -> None:
    """只允许撤销空的文件模块，存在条目或原文件记录时阻止破坏性降级。"""
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM file_entries) OR EXISTS(SELECT 1 FROM file_blobs)")):
        raise RuntimeError("存在文件业务数据，请先备份并清理后再降级；迁移不会删除磁盘原文件")
    for code in PERMISSIONS:
        connection.execute(sa.text("DELETE FROM role_permissions WHERE permission_id=:id"), {"id": seed_id("permission", code)})
        connection.execute(sa.text("DELETE FROM permissions WHERE id=:id"), {"id": seed_id("permission", code)})
    op.drop_table("file_entries")
    op.drop_table("file_blobs")
    op.drop_table("file_upload_policies")
    op.drop_table("file_spaces")
