"""权限模块的部门、角色、操作目录及授权关系；个人资源归属仍由各业务表维护。"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.entities import Base


class Department(Base):
    """独立部门资料；成员归属位于 users，管理员位于 user_roles。"""

    __tablename__ = "departments"
    __table_args__ = (CheckConstraint("length(btrim(name)) > 0 AND name = btrim(name)", name="ck_departments_name"),)
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Role(Base):
    """角色定义；binding_scope 约束绑定位置，不代表具体操作的资源范围。"""

    __tablename__ = "roles"
    __table_args__ = (CheckConstraint("binding_scope IN ('global', 'department')", name="ck_roles_binding_scope"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    binding_scope: Mapped[str] = mapped_column(String(20))


class Permission(Base):
    """可被授予的操作目录；代码不包含角色名或具体部门。"""

    __tablename__ = "permissions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(100))


class RolePermission(Base):
    """可复用的角色授权模板；范围解析时结合操作者与角色绑定。"""

    __tablename__ = "role_permissions"
    __table_args__ = (CheckConstraint("scope_type IN ('global', 'department', 'self')", name="ck_role_permissions_scope"),)

    role_id: Mapped[UUID] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    permission_id: Mapped[UUID] = mapped_column(ForeignKey("permissions.id"), primary_key=True)
    scope_type: Mapped[str] = mapped_column(String(20), primary_key=True)


class UserRole(Base):
    """当前有效角色绑定；部门绑定须与用户归属一致，撤销直接删除记录。"""

    __tablename__ = "user_roles"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role_id: Mapped[UUID] = mapped_column(ForeignKey("roles.id"))
    department_id: Mapped[UUID | None] = mapped_column(ForeignKey("departments.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


Index("uq_user_roles_global", UserRole.user_id, UserRole.role_id, unique=True,
      postgresql_where=text("department_id IS NULL"))
Index("uq_user_roles_department", UserRole.user_id, UserRole.role_id, UserRole.department_id,
      unique=True, postgresql_where=text("department_id IS NOT NULL"))
