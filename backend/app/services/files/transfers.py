"""文件传输编排：独立原件锁保护长传输，短事务负责鉴权、发布和失败恢复。"""

from contextlib import asynccontextmanager
import logging
from uuid import uuid4

import anyio

from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import RequestError, ServiceError
from app.models import FileBlob, FileEntry
from app.repositories import files as repository
from app.schemas.files import name_key, normalize_name, numbered_name

logger = logging.getLogger(__name__)


class FileTransfers:
    """以文件服务为业务入口，协调原件锁、磁盘和目录发布。"""

    def __init__(self, service):
        """保存文件服务；公开请求仍通过服务入口执行权限判断。"""
        self.service = service

    async def target(self, actor, space_id, parent_id):
        """在读取上传请求体前确认目标可写，并返回当前允许的文件大小。"""
        async with self.service.access.transaction(actor, space_id=space_id, operation="upload") as context:
            session, _, space, _, _ = context
            await self.service.parent(session, space, parent_id)
            return (await repository.policy(session, space.kind, space.department_id)).max_file_size_bytes

    async def abandon(self, blob_id):
        """回收尚未发布的原文件，提交结果不确定时保留已经 ready 的内容。"""
        try:
            with anyio.CancelScope(shield=True):
                with anyio.fail_after(5):
                    async with self.service.database.sessions.begin() as session:
                        blob = await session.get(FileBlob, blob_id)
                        if blob is not None and blob.state == "staging":
                            await self.service.storage.remove(blob.storage_key)
                            blob.state = "purged"
        except Exception:
            # 数据库或磁盘暂不可用时保留 staging，锁释放后由持久化清理扫描重试。
            logger.exception("未发布原文件回收失败 blob_id=%s", blob_id)

    async def upload(self, actor, space_id, parent_id, filename, chunks):
        """上传完整原文件后原子发布条目，取消、撤权和目录删除均不会发布半成品。"""
        try:
            filename = normalize_name(filename)
        except ValueError:
            raise RequestError(ErrorCode.INVALID_ARGUMENT) from None
        limit = await self.target(actor, space_id, parent_id)
        blob_id = uuid4()
        key = self.service.storage.key(blob_id)
        async with self.service.locks.hold(blob_id):
            try:
                async with self.service.database.sessions.begin() as session:
                    session.add(FileBlob(id=blob_id, storage_key=key))
                size, digest = await self.service.storage.write(key, chunks, limit)
                async with self.service.access.transaction(actor, space_id=space_id, operation="upload", write=True) as context:
                    session, user, space, _, _ = context
                    await self.service.parent(session, space, parent_id)
                    # 与策略修改锁定同一行，以事务提交先后明确新上限何时生效。
                    policy = await repository.policy(session, space.kind, space.department_id, lock=True)
                    if size > policy.max_file_size_bytes:
                        raise RequestError(ErrorCode.FILE_TOO_LARGE)
                    existing = set(await repository.children(session, space.id, parent_id))
                    name = filename
                    number = 0
                    while name_key(name) in existing:
                        number += 1
                        name = numbered_name(filename, number)
                    blob = await session.get(FileBlob, blob_id)
                    blob.state, blob.size_bytes, blob.sha256 = "ready", size, digest
                    row = FileEntry(space_id=space.id, parent_id=parent_id, kind="file", name=name,
                                    name_key=name_key(name), blob_id=blob_id, created_by=user.id)
                    session.add(row)
                    await session.flush()
                    result = await self.service.entry_info(session, row)
                return result
            except BaseException as error:
                await self.abandon(blob_id)
                if isinstance(error, (OSError, ValueError)):
                    raise ServiceError(ErrorCode.FILE_STORAGE_FAILED) from error
                raise

    @asynccontextmanager
    async def download(self, actor, entry_id):
        """在共享原件锁内提供已打开文件和元数据，后续撤权不打断已开始的下载。"""
        async with self.service.access.transaction(actor, entry_id=entry_id) as context:
            _, _, _, row, _ = context
            if row.kind != "file":
                raise RequestError(ErrorCode.INVALID_ARGUMENT)
            blob_id = row.blob_id
        async with self.service.locks.hold(blob_id, shared=True):
            async with self.service.access.transaction(actor, entry_id=entry_id) as context:
                session, _, _, row, _ = context
                blob = await session.get(FileBlob, blob_id)
                if blob is None or blob.state != "ready":
                    raise RequestError(ErrorCode.FILE_ENTRY_NOT_FOUND)
                info = await self.service.entry_info(session, row)
                key = blob.storage_key
            try:
                source = await self.service.storage.open_reader(key)
            except (OSError, ValueError) as error:
                raise ServiceError(ErrorCode.FILE_STORAGE_FAILED) from error
            try:
                yield info, source
            finally:
                with anyio.CancelScope(shield=True):
                    await source.aclose()
