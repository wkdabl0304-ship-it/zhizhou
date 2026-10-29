"""文件原件的跨进程读写锁；专用连接只持会话锁，不持长数据库事务。"""

import asyncio
from contextlib import asynccontextmanager
import hashlib
from uuid import UUID

import anyio
from sqlalchemy import func, select


def file_lock_key(blob_id: UUID) -> int:
    """为原文件生成独立命名空间的稳定有符号 64 位锁键。"""
    return int.from_bytes(hashlib.blake2b(b"zhizhou:file:" + blob_id.bytes, digest_size=8).digest(), "big", signed=True)


class FileLocks:
    """协调上传、下载及清理，多进程通过同一 PostgreSQL 实例同步。"""

    def __init__(self, engine):
        """绑定自动提交且使用 NullPool 的专用锁引擎。"""
        self.engine = engine

    @asynccontextmanager
    async def hold(self, blob_id: UUID, *, shared=False, wait=True):
        """在上下文内持有读写锁，清理可不等待，取消后始终回收物理连接。"""
        connection = await self.engine.connect()
        key = file_lock_key(blob_id)
        acquired = False
        suffix = "_shared" if shared else ""
        operation = getattr(func, ("pg_advisory_lock" if wait else "pg_try_advisory_lock") + suffix)
        try:
            result = await connection.scalar(select(operation(key)))
            acquired = wait or bool(result)
            yield acquired
        finally:
            with anyio.CancelScope(shield=True):
                try:
                    async with asyncio.timeout(5):
                        if acquired:
                            await connection.execute(select(getattr(func, "pg_advisory_unlock" + suffix)(key)))
                except BaseException:
                    await connection.invalidate()
                    raise
                finally:
                    await connection.close()
