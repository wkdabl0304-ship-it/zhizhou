"""建立首期 RBAC 与部门范围，回填旧身份并保留所有账号和个人内容。"""

from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op

revision = "0006_authorization"
down_revision = "0005_conversation_titles"
branch_labels = None
depends_on = None

# 迁移保留自己的冻结种子，不导入会随业务演进的运行时代码。
ROLES = {"user": ("普通用户", "global"), "super_admin": ("超级管理员", "global"),
         "department_admin": ("部门管理员", "department")}
PERMISSIONS = {
    "model:use": "使用模型", "model:manage": "管理模型",
    "conversation:create": "创建个人会话", "conversation:read": "读取个人会话",
    "conversation:update": "修改个人会话", "conversation:delete": "删除个人会话",
    "conversation:chat": "发送会话消息", "user:read": "查看账号资料",
    "user:set_active": "启停账号", "user:reset_password": "重置账号密码",
    "department:read": "查看部门", "department:create": "创建部门",
    "department:update": "修改部门", "department:delete": "删除部门",
    "department_member:read": "查看部门成员", "department_member:add": "加入部门成员",
    "department_member:remove": "移除部门成员", "role:assign": "授予管理员角色",
    "role:revoke": "撤销管理员角色",
}


def seed_id(kind: str, code: str):
    """为冻结种子生成稳定 UUID，便于迁移回填和检查，不依赖插入顺序。"""
    return uuid5(NAMESPACE_URL, f"zhizhou:{kind}:{code}")


def upgrade() -> None:
    """创建权限结构并把旧单角色账号转换为基础角色及可选的全局管理角色。"""
    op.create_table("departments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("length(btrim(name)) > 0 AND name = btrim(name)", name="ck_departments_name"))
    op.add_column("users", sa.Column("department_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_users_department", "users", "departments", ["department_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_users_department_id", "users", ["department_id"])
    op.add_column("users", sa.Column("token_version", sa.Integer(), nullable=False, server_default="1"))
    op.create_check_constraint("ck_users_token_version", "users", "token_version > 0")
    roles = op.create_table("roles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("binding_scope", sa.String(20), nullable=False),
        sa.CheckConstraint("binding_scope IN ('global', 'department')", name="ck_roles_binding_scope"))
    permissions = op.create_table("permissions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("code", sa.String(100), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False))
    grants = op.create_table("role_permissions",
        sa.Column("role_id", sa.Uuid(), sa.ForeignKey("roles.id"), primary_key=True),
        sa.Column("permission_id", sa.Uuid(), sa.ForeignKey("permissions.id"), primary_key=True),
        sa.Column("scope_type", sa.String(20), primary_key=True),
        sa.CheckConstraint("scope_type IN ('global', 'department', 'self')", name="ck_role_permissions_scope"))
    op.create_table("user_roles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role_id", sa.Uuid(), sa.ForeignKey("roles.id"), nullable=False),
        sa.Column("department_id", sa.Uuid(), sa.ForeignKey("departments.id", ondelete="RESTRICT")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"])
    op.create_index("ix_user_roles_department_id", "user_roles", ["department_id"])
    op.create_index("uq_user_roles_global", "user_roles", ["user_id", "role_id"], unique=True,
                    postgresql_where=sa.text("department_id IS NULL"))
    op.create_index("uq_user_roles_department", "user_roles", ["user_id", "role_id", "department_id"], unique=True,
                    postgresql_where=sa.text("department_id IS NOT NULL"))
    op.bulk_insert(roles, [{"id": seed_id("role", code), "code": code, "name": name, "binding_scope": scope}
                           for code, (name, scope) in ROLES.items()])
    op.bulk_insert(permissions, [{"id": seed_id("permission", code), "code": code, "name": name}
                                 for code, name in PERMISSIONS.items()])
    templates = []
    for code in PERMISSIONS:
        if code.startswith("conversation:") or code == "model:use":
            templates.append(("user", code, "self" if code.startswith("conversation:") else "global"))
        else:
            templates.append(("super_admin", code, "global"))
        if code in {"department:read", "department_member:read", "department_member:add", "department_member:remove"}:
            templates.append(("department_admin", code, "department"))
    op.bulk_insert(grants, [{"role_id": seed_id("role", role), "permission_id": seed_id("permission", permission),
                            "scope_type": scope} for role, permission, scope in templates])
    # MD5 仅用于回填绑定记录的独立 UUID，不用于密码、令牌或安全随机数。
    connection = op.get_bind()
    for code, condition in (("user", "TRUE"), ("super_admin", "role = 'super_admin'")):
        connection.execute(sa.text(f"""INSERT INTO user_roles (id, user_id, role_id)
            SELECT md5(id::text || :code)::uuid, id, :role_id FROM users WHERE {condition}"""),
            {"code": code, "role_id": seed_id("role", code)})
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.drop_column("users", "role")


def downgrade() -> None:
    """恢复旧单角色结构并保留超管身份；旧结构无法保留部门及部门授权。"""
    op.add_column("users", sa.Column("role", sa.String(20), nullable=False, server_default="user"))
    op.execute("""UPDATE users SET role = 'super_admin' WHERE EXISTS (
        SELECT 1 FROM user_roles ur JOIN roles r ON r.id = ur.role_id
        WHERE ur.user_id = users.id AND r.code = 'super_admin' AND ur.department_id IS NULL)""")
    op.create_check_constraint("ck_users_role", "users", "role IN ('user', 'super_admin')")
    op.drop_table("user_roles")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_constraint("ck_users_token_version", "users", type_="check")
    op.drop_column("users", "token_version")
    op.drop_index("ix_users_department_id", table_name="users")
    op.drop_constraint("fk_users_department", "users", type_="foreignkey")
    op.drop_column("users", "department_id")
    op.drop_table("departments")
