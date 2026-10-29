"""文件空间的权限和短事务边界；角色授予交给已有统一授权服务。"""

from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import select

from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import RequestError
from app.models import Department, FileSpace, User
from app.repositories import files as repository
from app.schemas.files import SpaceInfo
from app.services.authorization import AuthorizationService, management_lock

OPERATIONS = ("read", "upload", "update", "delete")


def permitted(user, grants, space, operation: str) -> bool:
    """判断当前授权是否覆盖空间，个人内容始终限制本人，共享默认规则单独表达。"""
    if space.kind == "personal":
        return space.owner_id == user.id and any(grant.permission == f"file:{operation}"
            and grant.scope_type == "self" and grant.scope_id == user.id for grant in grants)
    if operation == "read" and (space.kind == "global" or space.department_id == user.department_id):
        return True
    return any(grant.permission == f"file:{operation}" and (grant.scope_type == "global" or
        grant.scope_type == "department" and space.kind == "department" and grant.scope_id == space.department_id)
        for grant in grants)


class FileAccess:
    """为文件操作统一确认最新身份、可见性及目录写入的锁顺序。"""

    def __init__(self, database):
        """复用数据库及授权服务，不保存请求身份或权限缓存。"""
        self.database = database
        self.authorization = AuthorizationService(database)

    @asynccontextmanager
    async def transaction(self, actor: User, *, space_id: UUID | None = None,
                          entry_id: UUID | None = None, operation="read", write=False):
        """在管理共享锁和空间读写锁内提供已授权短事务。

        锁顺序始终为管理锁、空间锁；写请求在等待空间锁后重读条目，避免
        使用等待期间已删除或改名的快照。文件流传输不得在此上下文中进行。
        """
        async with self.database.sessions.begin() as session:
            await management_lock(session, shared=True)
            user = await self.authorization.current(session, actor)
            grants = await self.authorization.grants(session, user)
            row = None
            hidden = ErrorCode.FILE_ENTRY_NOT_FOUND if entry_id else ErrorCode.FILE_SPACE_NOT_FOUND
            if entry_id is not None:
                row = await repository.entry(session, entry_id)
                if row is None:
                    raise RequestError(hidden)
                space_id = row.space_id
            space = await session.scalar(select(FileSpace).where(FileSpace.id == space_id,
                    FileSpace.deleted_at.is_(None)).with_for_update(read=not write))
            if space is None or not permitted(user, grants, space, "read"):
                raise RequestError(hidden)
            if entry_id is not None:
                session.expire(row)
                row = await repository.entry(session, entry_id)
                if row is None:
                    raise RequestError(hidden)
            if not permitted(user, grants, space, operation):
                raise RequestError(ErrorCode.FORBIDDEN)
            yield session, user, space, row, grants

    async def info(self, session, user, space, grants) -> SpaceInfo:
        """构造空间显示名称、有效大小上限和当前操作能力。"""
        if space.kind == "global":
            name = "全局空间"
        elif space.kind == "personal":
            name = "个人空间"
        else:
            name = (await session.get(Department, space.department_id)).name
        policy = await repository.policy(session, space.kind, space.department_id)
        return SpaceInfo(id=space.id, kind=space.kind, name=name, department_id=space.department_id,
                         owner_id=space.owner_id, max_file_size_bytes=policy.max_file_size_bytes,
                         capabilities=[operation for operation in OPERATIONS if permitted(user, grants, space, operation)])
