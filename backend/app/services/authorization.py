"""统一授权服务：解析 RBAC 范围、构造身份以及串行化权限管理事务，不提供角色通配符。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import RequestError
from app.db.business import BusinessDatabase
from app.models import Department, User, UserRole
from app.repositories import authorization as repository
from app.repositories import users
from app.schemas.auth import UserInfo
from app.schemas.authorization import DepartmentBrief, Grant

# 第一版管理写入统一排队，跨进程共用事务锁，确保撤权检查与写入之间不可插入管理变更。
# 独立命名空间的固定键不复用会话执行锁；短事务结束自动释放，不持锁等待模型。
MANAGEMENT_LOCK_KEY = 625915041947204


async def management_lock(session: AsyncSession, *, shared: bool = False) -> None:
    """取得权限管理事务锁，共享锁用于请求读取，独占锁用于授权及管理写入。"""
    operation = func.pg_advisory_xact_lock_shared if shared else func.pg_advisory_xact_lock
    await session.execute(select(operation(MANAGEMENT_LOCK_KEY)))


class AuthorizationService:
    """基于当前数据库状态判断操作权限，不从 JWT 或角色名称推断业务权限。"""

    def __init__(self, database: BusinessDatabase):
        """绑定 Session 工厂，不保存请求级身份、授权缓存或事务。"""
        self.database = database

    async def current(self, session: AsyncSession, actor: User | UUID) -> User:
        """重新确认账号及可选凭据版本，管理事务等待锁后也不能复用过期身份。"""
        user_id = actor if isinstance(actor, UUID) else actor.id
        expected_version = actor.token_version if not isinstance(actor, UUID) else None
        user = await users.by_id(session, user_id)
        if user is None or not user.is_active or (expected_version is not None and user.token_version != expected_version):
            raise RequestError(ErrorCode.UNAUTHENTICATED)
        return user

    async def grants(self, session: AsyncSession, user: User) -> list[Grant]:
        """把角色模板解析为具体范围，并合并多角色带来的重复授权。"""
        resolved = set()
        for permission, scope, department_id in await repository.grants_for(session, user.id):
            scope_id = user.id if scope == "self" else department_id if scope == "department" else None
            resolved.add((permission, scope, scope_id))
        return [Grant(permission=permission, scope_type=scope, scope_id=scope_id)
                for permission, scope, scope_id in sorted(resolved, key=_grant_sort_key)]

    async def require(self, session: AsyncSession, actor: User | UUID, permission: str, *,
                      department_id: UUID | None = None, owner_id: UUID | None = None,
                      hidden: ErrorCode | None = None) -> User:
        """校验具体操作是否覆盖目标范围；隐藏资源入口可指定安全的未找到错误。"""
        user = await self.current(session, actor)
        for grant in await self.grants(session, user):
            if grant.permission != permission:
                continue
            if (grant.scope_type == "global"
                or grant.scope_type == "department" and department_id is not None and grant.scope_id == department_id
                or grant.scope_type == "self" and owner_id is not None and grant.scope_id == owner_id):
                return user
        raise RequestError(hidden or ErrorCode.FORBIDDEN)

    async def info(self, session: AsyncSession, user: User) -> UserInfo:
        """构造本人公开身份，旧 role 字段仅用于兼容展示，正式授权来自 grants。"""
        role_codes = sorted({row.code for row in await repository.roles_for(session, user.id)})
        department = await session.get(Department, user.department_id) if user.department_id else None
        return UserInfo(id=user.id, username=user.username,
                        role="super_admin" if "super_admin" in role_codes else "user",
                        department=DepartmentBrief.model_validate(department) if department else None,
                        roles=role_codes, grants=await self.grants(session, user))

    async def bind(self, session: AsyncSession, user: User, code: str, department_id: UUID | None = None) -> None:
        """按角色定义幂等绑定身份；这是角色生命周期配置，不用于判断操作权限。"""
        role = await repository.role_by_code(session, code)
        if (role.binding_scope == "global" and department_id is not None
            or role.binding_scope == "department" and (department_id is None or user.department_id != department_id)):
            raise RequestError(ErrorCode.TARGET_STATE_CONFLICT)
        if await repository.binding(session, user.id, role.id, department_id) is None:
            session.add(UserRole(user_id=user.id, role_id=role.id, department_id=department_id))
            await session.flush()

    @asynccontextmanager
    async def transaction(self, actor: User, permission: str, *, department_id: UUID | None = None,
                          shared: bool = False, hidden: ErrorCode | None = None) -> AsyncIterator[AsyncSession]:
        """在管理锁内重新授权并提供事务，提交或异常回滚时自动释放锁。"""
        async with self.database.sessions.begin() as session:
            await management_lock(session, shared=shared)
            await self.require(session, actor, permission, department_id=department_id, hidden=hidden)
            yield session


def _grant_sort_key(value):
    """稳定排序已解析授权，使身份响应和分页范围指纹不受查询返回顺序影响。"""
    return value[0], value[1], str(value[2] or "")
