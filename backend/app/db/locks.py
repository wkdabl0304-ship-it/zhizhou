"""跨进程会话互斥，使用独立异步连接上的 PostgreSQL advisory lock。"""

import asyncio
import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

import anyio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine


def lock_key(conversation_id: UUID) -> int:
    """生成跨进程一致的有符号锁键；不用每个 Python 进程随机化的 hash()。"""
    digest = hashlib.blake2b(
        b"zhizhou:conversation:" + conversation_id.bytes, digest_size=8
    ).digest()
    return int.from_bytes(digest, "big", signed=True)


class ConversationLocks:
    """非阻塞锁管理器；独立 NullPool 引擎确保物理连接关闭时解除服务端锁。"""

    def __init__(self, engine: AsyncEngine) -> None:
        """保存自动提交的专用异步引擎，不借用 ORM 事务连接。"""
        self.engine = engine

    @asynccontextmanager
    async def hold(self, conversation_id: UUID) -> AsyncIterator[bool]:
        """尝试持锁并返回是否取得；退出屏蔽取消，解锁失败则失效物理连接。"""
        connection = await self.engine.connect()
        acquired = False
        key = lock_key(conversation_id)
        try:
            acquired = bool(
                await connection.scalar(select(func.pg_try_advisory_lock(key)))
            )
            yield acquired
        finally:
            with anyio.CancelScope(shield=True):
                try:
                    async with asyncio.timeout(5):
                        if acquired:
                            await connection.execute(
                                select(func.pg_advisory_unlock(key))
                            )
                except BaseException:
                    await connection.invalidate()
                    raise
                finally:
                    await connection.close()
