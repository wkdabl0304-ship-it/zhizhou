"""共享文件业务入口：目录树、空间分页及条目操作，传输和清理由专职组件编排。"""

from sqlalchemy import and_, false, or_, select

from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import RequestError
from app.db.file_locks import FileLocks
from app.models import FileBlob, FileEntry, FileSpace
from app.repositories import files as repository
from app.schemas.authorization import Page
from app.schemas.files import Breadcrumb, DirectoryPage, EntryDetail, EntryInfo, name_key
from app.services.authorization import management_lock
from app.services.files.access import FileAccess
from app.services.files.cleanup import FileCleanup
from app.services.files.pagination import page
from app.services.files.policies import UploadPolicies
from app.services.files.transfers import FileTransfers


class FileService:
    """复用统一身份和授权，为 HTTP 及未来智能体提供相同的文件业务边界。"""

    def __init__(self, database, storage):
        """组装轻量文件服务，不连接磁盘、不启动后台任务或缓存账号权限。"""
        self.database = database
        self.storage = storage
        self.access = FileAccess(database)
        self.locks = FileLocks(database.lock_engine)
        self.policies = UploadPolicies(self.access)
        self.transfers = FileTransfers(self)
        self.cleanup = FileCleanup(database, storage, self.locks)

    async def spaces(self, actor, *, limit=20, cursor=None):
        """分页列出当前可读空间，超级管理员也只能看到本人的个人空间。"""
        async with self.database.sessions.begin() as session:
            await management_lock(session, shared=True)
            user = await self.access.authorization.current(session, actor)
            grants = await self.access.authorization.grants(session, user)
            shared_global = any(grant.permission == "file:read" and grant.scope_type == "global" for grant in grants)
            departments = {grant.scope_id for grant in grants if grant.permission == "file:read" and grant.scope_type == "department"}
            if user.department_id:
                departments.add(user.department_id)
            personal_read = any(grant.permission == "file:read" and grant.scope_type == "self"
                                and grant.scope_id == user.id for grant in grants)
            visible = [and_(FileSpace.kind == "personal", FileSpace.owner_id == user.id) if personal_read else false(),
                       FileSpace.kind == "global"]
            visible.append(FileSpace.kind == "department" if shared_global else
                           and_(FileSpace.kind == "department", FileSpace.department_id.in_(departments)))
            statement = select(FileSpace).where(FileSpace.deleted_at.is_(None), or_(*visible))
            rows, next_cursor = await page(session, statement, FileSpace, user, grants,
                kind="spaces", filters={}, limit=limit, cursor=cursor)
            return Page(items=[await self.access.info(session, user, space, grants) for space in rows], next_cursor=next_cursor)

    async def space(self, actor, space_id):
        """读取空间归属、有效上传限制和当前账号的操作能力。"""
        async with self.access.transaction(actor, space_id=space_id) as context:
            session, user, space, _, grants = context
            return await self.access.info(session, user, space, grants)

    async def parent(self, session, space, parent_id):
        """验证指定父节点是同空间有效目录，根目录以空标识表示。"""
        if parent_id is None:
            return None
        row = await repository.entry(session, parent_id)
        if row is None or row.space_id != space.id:
            raise RequestError(ErrorCode.FILE_ENTRY_NOT_FOUND)
        if row.kind != "folder":
            raise RequestError(ErrorCode.INVALID_ARGUMENT)
        return row

    async def breadcrumbs(self, session, space, parent_id):
        """按根到当前目录构造可见目录链，拒绝损坏的循环父关系。"""
        result = []
        seen = set()
        while parent_id is not None:
            if parent_id in seen:
                raise RequestError(ErrorCode.INVALID_ARGUMENT)
            seen.add(parent_id)
            row = await self.parent(session, space, parent_id)
            result.append(Breadcrumb(id=row.id, name=row.name))
            parent_id = row.parent_id
        return list(reversed(result))

    async def entry_info(self, session, row):
        """构造不含原件键的条目信息，从原件记录读取文件实际大小。"""
        size = None
        if row.blob_id is not None:
            size = (await session.get(FileBlob, row.blob_id)).size_bytes
        return EntryInfo(id=row.id, space_id=row.space_id, parent_id=row.parent_id, kind=row.kind,
            name=row.name, size_bytes=size, created_by=row.created_by, version=row.version,
            created_at=row.created_at, updated_at=row.updated_at)

    async def directory(self, actor, space_id, *, parent_id=None, limit=20, cursor=None):
        """浏览一层目录及面包屑，每页都重新判断当前身份及空间读取范围。"""
        async with self.access.transaction(actor, space_id=space_id) as context:
            session, user, space, _, grants = context
            await self.parent(session, space, parent_id)
            statement = select(FileEntry).where(FileEntry.space_id == space.id,
                FileEntry.parent_id == parent_id, FileEntry.deleted_at.is_(None))
            rows, next_cursor = await page(session, statement, FileEntry, user, grants,
                kind="entries", filters={"space_id": space.id, "parent_id": parent_id}, limit=limit, cursor=cursor)
            return DirectoryPage(space=await self.access.info(session, user, space, grants), parent_id=parent_id,
                breadcrumbs=await self.breadcrumbs(session, space, parent_id),
                items=[await self.entry_info(session, row) for row in rows], next_cursor=next_cursor)

    async def detail(self, actor, entry_id):
        """读取文件或目录详情，目录的面包屑包含当前目录自身。"""
        async with self.access.transaction(actor, entry_id=entry_id) as context:
            session, _, space, row, _ = context
            return EntryDetail(entry=await self.entry_info(session, row), breadcrumbs=await self.breadcrumbs(
                session, space, row.id if row.kind == "folder" else row.parent_id))

    async def folder(self, actor, space_id, body):
        """在可写目录创建子目录，文件与目录共用忽略大小写的名称集合。"""
        async with self.access.transaction(actor, space_id=space_id, operation="upload", write=True) as context:
            session, user, space, _, _ = context
            await self.parent(session, space, body.parent_id)
            key = name_key(body.name)
            if key in await repository.children(session, space.id, body.parent_id):
                raise RequestError(ErrorCode.FILE_NAME_EXISTS)
            row = FileEntry(space_id=space.id, parent_id=body.parent_id, kind="folder", name=body.name,
                            name_key=key, created_by=user.id)
            session.add(row)
            await session.flush()
            return await self.entry_info(session, row)

    async def rename(self, actor, entry_id, body):
        """按版本重命名条目，只变更显示元数据，不移动原文件或子目录。"""
        async with self.access.transaction(actor, entry_id=entry_id, operation="update", write=True) as context:
            session, _, space, row, _ = context
            if row.version != body.version:
                raise RequestError(ErrorCode.FILE_ENTRY_VERSION_CONFLICT)
            if row.name != body.name:
                key = name_key(body.name)
                if key != row.name_key and key in await repository.children(session, space.id, row.parent_id):
                    raise RequestError(ErrorCode.FILE_NAME_EXISTS)
                row.name, row.name_key = body.name, key
                row.version += 1
                await session.flush()
            return await self.entry_info(session, row)

    async def delete(self, actor, entry_id, version):
        """按版本逻辑删除文件或整棵目录，清理状态与可见性在同一事务提交。"""
        async with self.access.transaction(actor, entry_id=entry_id, operation="delete", write=True) as context:
            session, _, _, row, _ = context
            if row.version != version:
                raise RequestError(ErrorCode.FILE_ENTRY_VERSION_CONFLICT)
            await repository.delete_tree(session, row)
