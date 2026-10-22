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
    """将业务会话 ID 转换为 PostgreSQL 会话锁使用的整数键。

    对固定命名空间和 UUID 字节计算 64 位摘要，返回有符号整数；同一会话
    在不同进程中得到相同键，不使用进程间可能不同的 Python hash()。
    """
    digest = hashlib.blake2b(
        b"zhizhou:conversation:" + conversation_id.bytes, digest_size=8
    ).digest()
    return int.from_bytes(digest, "big", signed=True)


class ConversationLocks:
    """非阻塞锁管理器；独立 NullPool 引擎确保物理连接关闭时解除服务端锁。"""

    def __init__(self, engine: AsyncEngine) -> None:
        """初始化跨进程会话锁管理器，供会话服务协调生成与删除操作。

        engine 应为使用自动提交和 NullPool 的专用异步引擎；这里只保存
        引擎，实际持锁时才打开连接，不借用 ORM 事务连接。
        """
        self.engine = engine

    @asynccontextmanager
    async def hold(self, conversation_id: UUID) -> AsyncIterator[bool]:
        """在上下文期间尝试独占指定会话，防止多个执行者同时修改它。

        为 conversation_id 打开专用连接，非阻塞地尝试 advisory lock，
        yield 的布尔值表示是否取得，未取得时由调用方决定拒绝或跳过。
        退出时屏蔽取消并尝试解锁；解锁失败会使连接失效并传播异常，
        最终关闭连接，避免会话锁残留。
        """
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
