"""用户管理服务：账号白名单、启停、改密及全局管理员任免，保护最后一名可用超管。"""

from uuid import UUID

from anyio import to_thread
from pwdlib import PasswordHash
from sqlalchemy import func, select

from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import RequestError
from app.db.business import BusinessDatabase
from app.models import User, UserRole
from app.repositories import authorization as repository
from app.schemas.authorization import Page, PasswordReset
from app.services.authorization import AuthorizationService, management_lock
from app.services.management import managed_user, paginate, target_user


async def protect_last_admin(session, target: User) -> None:
    """禁止移除最后一名启用超管的可用性；调用方必须已取得独占管理锁。"""
    role = await repository.role_by_code(session, "super_admin")
    if not target.is_active or await repository.binding(session, target.id, role.id, None) is None:
        return
    count = await session.scalar(select(func.count()).select_from(UserRole).join(User, User.id == UserRole.user_id)
        .where(UserRole.role_id == role.id, UserRole.department_id.is_(None), User.is_active.is_(True)))
    if count <= 1:
        raise RequestError(ErrorCode.LAST_SUPER_ADMIN)


async def grant_super_admin(database: BusinessDatabase, username: str) -> None:
    """为运维已确认的启用账号幂等授予超管；只供本地命令和可信测试初始化使用。"""
    authorization = AuthorizationService(database)
    async with database.sessions.begin() as session:
        await management_lock(session)
        user = await session.scalar(select(User).where(User.username == username).with_for_update())
        if user is None:
            raise RequestError(ErrorCode.USER_NOT_FOUND)
        if not user.is_active:
            raise RequestError(ErrorCode.TARGET_STATE_CONFLICT)
        await authorization.bind(session, user, "super_admin")


class UserManagementService:
    """封装受全局权限保护的用户操作，不提供账号删除或个人内容查询。"""

    def __init__(self, database: BusinessDatabase):
        """绑定数据库、授权服务和密码工具，不创建请求事务。"""
        self.database = database
        self.authorization = AuthorizationService(database)
        self.passwords = PasswordHash.recommended()

    async def list(self, actor: User, *, search: str | None = None, is_active: bool | None = None,
                   department_id: UUID | None = None, unassigned: bool = False, limit: int = 20, cursor: str | None = None):
        """分页查询全站账号管理资料，筛选条件和有效授权共同约束分页游标。"""
        if unassigned and department_id is not None:
            raise RequestError(ErrorCode.INVALID_ARGUMENT)
        search = search.strip().lower() if search else None
        async with self.authorization.transaction(actor, "user:read", shared=True) as session:
            current = await self.authorization.current(session, actor)
            statement = select(User)
            if search:
                statement = statement.where(User.username.contains(search, autoescape=True))
            if is_active is not None:
                statement = statement.where(User.is_active == is_active)
            if department_id is not None:
                statement = statement.where(User.department_id == department_id)
            elif unassigned:
                statement = statement.where(User.department_id.is_(None))
            rows, next_cursor = await paginate(session, self.authorization, current, statement, User, kind="users",
                filters={"search": search, "is_active": is_active, "department_id": department_id, "unassigned": unassigned},
                limit=limit, cursor=cursor)
            return Page(items=[await managed_user(session, row) for row in rows], next_cursor=next_cursor)

    async def get(self, actor: User, user_id: UUID):
        """读取单个账号的管理资料，不公开该用户个人资源。"""
        async with self.authorization.transaction(actor, "user:read", shared=True) as session:
            user = await session.get(User, user_id)
            if user is None:
                raise RequestError(ErrorCode.USER_NOT_FOUND)
            return await managed_user(session, user)

    async def set_active(self, actor: User, user_id: UUID, active: bool):
        """幂等设置账号状态，停用时撤销旧令牌并保护最后一名可用超管。"""
        async with self.authorization.transaction(actor, "user:set_active") as session:
            target = await target_user(session, user_id)
            if target.is_active != active:
                if not active:
                    await protect_last_admin(session, target)
                    target.token_version += 1
                target.is_active = active
                await session.flush()
                await session.refresh(target)
            return await managed_user(session, target)

    async def reset_password(self, actor: User, user_id: UUID, body: PasswordReset) -> None:
        """设置新密码并撤销全部旧令牌，保持启停状态，哈希计算不占用管理事务。"""
        # 先拒绝无权限请求，避免未授权用户借改密入口触发昂贵密码哈希。
        async with self.authorization.transaction(actor, "user:reset_password", shared=True):
            pass
        encoded = await to_thread.run_sync(self.passwords.hash, body.password)
        async with self.authorization.transaction(actor, "user:reset_password") as session:
            target = await target_user(session, user_id)
            target.password_hash = encoded
            target.token_version += 1

    async def set_super_admin(self, actor: User, user_id: UUID, *, enabled: bool) -> None:
        """授予或撤销全局管理角色，重复操作幂等且不能撤销最后的可用管理能力。"""
        async with self.authorization.transaction(actor, "role:assign" if enabled else "role:revoke") as session:
            target = await target_user(session, user_id)
            if enabled:
                if not target.is_active:
                    raise RequestError(ErrorCode.TARGET_STATE_CONFLICT)
                await self.authorization.bind(session, target, "super_admin")
            else:
                await protect_last_admin(session, target)
                role = await repository.role_by_code(session, "super_admin")
                assignment = await repository.binding(session, target.id, role.id, None)
                if assignment is not None:
                    await session.delete(assignment)
