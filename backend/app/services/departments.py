"""部门管理服务：范围可见性、成员归属与部门管理员生命周期，写入统一使用管理事务锁。"""

from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import RequestError
from app.db.business import BusinessDatabase
from app.models import Department, User, UserRole
from app.repositories import authorization as repository
from app.repositories import files as file_repository
from app.schemas.authorization import DepartmentInfo, DepartmentWrite, Page
from app.services.authorization import AuthorizationService, management_lock
from app.services.management import member_info, paginate, target_user


async def department_row(session, department_id: UUID, *, lock: bool = False) -> Department:
    """读取或锁定部门，缺失时统一报告部门不可用。"""
    statement = select(Department).where(Department.id == department_id)
    row = await session.scalar(statement.with_for_update() if lock else statement)
    if row is None:
        raise RequestError(ErrorCode.DEPARTMENT_NOT_FOUND)
    return row


class DepartmentService:
    """封装部门资料、直接加入成员以及部门角色任免，不访问任何成员个人内容。"""

    def __init__(self, database: BusinessDatabase):
        """绑定数据库与统一授权服务，不缓存用户当前部门。"""
        self.database = database
        self.authorization = AuthorizationService(database)

    async def list(self, actor: User, *, limit: int = 20, cursor: str | None = None):
        """分页返回授权可见部门；无部门查看权限的用户得到 403。"""
        async with self.database.sessions.begin() as session:
            await management_lock(session, shared=True)
            current = await self.authorization.current(session, actor)
            grants = [grant for grant in await self.authorization.grants(session, current) if grant.permission == "department:read"]
            global_access = any(grant.scope_type == "global" for grant in grants)
            department_ids = {grant.scope_id for grant in grants if grant.scope_type == "department"}
            if not global_access and not department_ids:
                raise RequestError(ErrorCode.FORBIDDEN)
            statement = select(Department)
            if not global_access:
                statement = statement.where(Department.id.in_(department_ids))
            rows, next_cursor = await paginate(session, self.authorization, current, statement, Department,
                kind="departments", filters={}, limit=limit, cursor=cursor)
            return Page(items=[DepartmentInfo.model_validate(row) for row in rows], next_cursor=next_cursor)

    async def get(self, actor: User, department_id: UUID):
        """读取授权覆盖的部门资料，隐藏其他部门是否存在。"""
        async with self.authorization.transaction(actor, "department:read", department_id=department_id,
                shared=True, hidden=ErrorCode.DEPARTMENT_NOT_FOUND) as session:
            return DepartmentInfo.model_validate(await department_row(session, department_id))

    async def save(self, actor: User, body: DepartmentWrite, department_id: UUID | None = None):
        """创建或改名部门，以数据库唯一约束处理并发重名，失败整体回滚。"""
        try:
            async with self.authorization.transaction(actor, "department:create" if department_id is None else "department:update") as session:
                if department_id is None:
                    row = Department(name=body.name)
                    session.add(row)
                else:
                    row = await department_row(session, department_id, lock=True)
                    row.name = body.name
                await session.flush()
                if department_id is None:
                    await file_repository.create_department_space(session, row.id)
                return DepartmentInfo.model_validate(row)
        except IntegrityError as error:
            if getattr(error.orig, "sqlstate", None) == "23505":
                raise RequestError(ErrorCode.DEPARTMENT_NAME_EXISTS) from None
            raise

    async def delete(self, actor: User, department_id: UUID) -> None:
        """原子删除部门及共享资料并解除部门归属授权，保留账号和个人内容。"""
        async with self.authorization.transaction(actor, "department:delete") as session:
            row = await department_row(session, department_id, lock=True)
            await file_repository.close_department_space(session, department_id)
            await session.execute(delete(UserRole).where(UserRole.department_id == department_id))
            await session.execute(update(User).where(User.department_id == department_id).values(department_id=None))
            await session.delete(row)

    async def members(self, actor: User, department_id: UUID, *, search: str | None = None,
                      limit: int = 20, cursor: str | None = None):
        """分页读取指定可见部门的成员白名单，不提供全站账号搜索。"""
        search = search.strip().lower() if search else None
        async with self.authorization.transaction(actor, "department_member:read", department_id=department_id,
                shared=True, hidden=ErrorCode.DEPARTMENT_NOT_FOUND) as session:
            await department_row(session, department_id)
            current = await self.authorization.current(session, actor)
            statement = select(User).where(User.department_id == department_id)
            if search:
                statement = statement.where(User.username.contains(search, autoescape=True))
            rows, next_cursor = await paginate(session, self.authorization, current, statement, User,
                kind="members", filters={"department_id": department_id, "search": search}, limit=limit, cursor=cursor)
            return Page(items=[await member_info(session, row) for row in rows], next_cursor=next_cursor)

    async def add_member(self, actor: User, department_id: UUID, username: str):
        """按完整用户名立即加入启用账号；同部门重复加入幂等，跨部门必须先移除。"""
        async with self.authorization.transaction(actor, "department_member:add", department_id=department_id) as session:
            await department_row(session, department_id, lock=True)
            target = await session.scalar(select(User).where(User.username == username).with_for_update())
            if target is None:
                raise RequestError(ErrorCode.USER_NOT_FOUND)
            if not target.is_active:
                raise RequestError(ErrorCode.TARGET_STATE_CONFLICT)
            if target.department_id not in (None, department_id):
                raise RequestError(ErrorCode.USER_IN_OTHER_DEPARTMENT)
            target.department_id = department_id
            await session.flush()
            return await member_info(session, target)

    async def remove_member(self, actor: User, department_id: UUID, user_id: UUID) -> None:
        """移除成员及该部门的全部角色绑定；无部门时幂等，其他部门成员不可被影响。"""
        async with self.authorization.transaction(actor, "department_member:remove", department_id=department_id) as session:
            await department_row(session, department_id, lock=True)
            target = await target_user(session, user_id)
            if target.department_id not in (None, department_id):
                raise RequestError(ErrorCode.TARGET_STATE_CONFLICT)
            await session.execute(delete(UserRole).where(UserRole.user_id == user_id, UserRole.department_id == department_id))
            target.department_id = None

    async def set_administrator(self, actor: User, department_id: UUID, user_id: UUID, *, enabled: bool) -> None:
        """幂等任免部门管理员；授予要求启用成员，撤销不影响账号级角色。"""
        async with self.authorization.transaction(actor, "role:assign" if enabled else "role:revoke") as session:
            await department_row(session, department_id, lock=True)
            target = await target_user(session, user_id)
            if enabled:
                if not target.is_active or target.department_id != department_id:
                    raise RequestError(ErrorCode.TARGET_STATE_CONFLICT)
                await self.authorization.bind(session, target, "department_admin", department_id)
            else:
                role = await repository.role_by_code(session, "department_admin")
                assignment = await repository.binding(session, user_id, role.id, department_id)
                if assignment is not None:
                    await session.delete(assignment)
