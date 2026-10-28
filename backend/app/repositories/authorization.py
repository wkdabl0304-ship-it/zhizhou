"""权限仓储：查询角色模板与有效绑定，只执行 SQL，事务和业务错误由服务决定。"""

from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Permission, Role, RolePermission, User, UserRole


def valid_binding():
    """筛除绑定位置错误或部门归属失配的授权，数据库脏数据也不能扩大访问范围。"""
    return or_(
        and_(Role.binding_scope == "global", UserRole.department_id.is_(None)),
        and_(Role.binding_scope == "department", UserRole.department_id.is_not(None),
             UserRole.department_id == User.department_id),
    )


async def roles_for(session: AsyncSession, user_id: UUID):
    """读取用户当前有效的角色定义和绑定位置，不把失效的旧部门授权返回给调用者。"""
    return (await session.execute(
        select(Role.code, Role.binding_scope, UserRole.department_id)
        .join(UserRole, UserRole.role_id == Role.id).join(User, User.id == UserRole.user_id)
        .where(User.id == user_id, valid_binding()).order_by(Role.code)
    )).all()


async def grants_for(session: AsyncSession, user_id: UUID):
    """读取实际授权模板及绑定部门，具体 self 范围由服务结合当前用户解析。"""
    return (await session.execute(
        select(Permission.code, RolePermission.scope_type, UserRole.department_id)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, Role.id == RolePermission.role_id)
        .join(UserRole, UserRole.role_id == Role.id).join(User, User.id == UserRole.user_id)
        .where(User.id == user_id, valid_binding(), or_(
            and_(Role.binding_scope == "global", RolePermission.scope_type.in_(["global", "self"])),
            and_(Role.binding_scope == "department", RolePermission.scope_type == "department")))
        .order_by(Permission.code, RolePermission.scope_type)
    )).all()


async def role_by_code(session: AsyncSession, code: str) -> Role:
    """取得内置角色，缺少迁移种子时立即报错，避免默默创建不完整授权。"""
    return (await session.scalars(select(Role).where(Role.code == code))).one()


async def binding(session: AsyncSession, user_id: UUID, role_id: UUID, department_id: UUID | None):
    """查找精确角色绑定，供服务实现重复授予和撤销的幂等行为。"""
    return await session.scalar(select(UserRole).where(
        UserRole.user_id == user_id, UserRole.role_id == role_id, UserRole.department_id == department_id))
