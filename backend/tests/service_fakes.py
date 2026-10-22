"""HTTP 与传输测试的会话服务替身；真实 ORM、归属与锁由 PostgreSQL 集成测试覆盖。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from app.services.conversations import ConversationService, PreparedChat

A = "00000000-0000-4000-8000-000000000001"
B = "00000000-0000-4000-8000-000000000002"
OVERRIDE = "00000000-0000-4000-8000-000000000003"


class MemoryConversationService(ConversationService):
    """保留正式流聚合逻辑，仅替换数据库提交，避免传输回归依赖外部服务。"""

    def __init__(self, database=None):
        """不创建数据库资源，记录快照提交以便观察完成确认的边界。"""
        self.saved = []

    async def recover(self):
        """替身不跨进程持久化，因此没有待恢复轮次。"""

    @asynccontextmanager
    async def prepare(
        self, user_id, message, conversation_id
    ) -> AsyncIterator[PreparedChat]:
        """模拟后端签发 ID 与请求退出清理，业务归属校验不由此替身模拟。"""
        prepared = PreparedChat(
            conversation_id or uuid4(), uuid4(), message, conversation_id is None
        )
        try:
            yield prepared
        finally:
            if not prepared.terminal:
                await self.persist(prepared, status="interrupted")

    async def persist(
        self, prepared, *, status="running", response=None, error_code=None
    ):
        """记录一次提交并设置终止标记，不访问外部数据库。"""
        self.saved.append((prepared.turn_id, status))
        prepared.terminal = status != "running"
