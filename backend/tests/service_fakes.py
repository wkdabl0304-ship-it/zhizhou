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
        """初始化内存会话服务替身，供 HTTP 和流式测试隔离数据库。

        不调用正式服务的资源初始化，只建立提交记录列表，供断言观察
        最终完成事件与快照保存的先后顺序。
        """
        self.saved = []

    async def recover(self):
        """替代正式服务的启动恢复入口；内存替身没有持久化轮次，因此不执行恢复。"""

    @asynccontextmanager
    async def prepare(
        self, user_id, message, conversation_id
    ) -> AsyncIterator[PreparedChat]:
        """提供测试用聊天上下文，让路由无需真实数据库即可执行流式响应。

        缺少会话 ID 时生成随机标识，yield PreparedChat 后在退出时保存
        尚未终止的中断状态；所有权和跨进程锁不在此替身中模拟。
        """
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
        """模拟业务历史保存，供测试观察提交次数与终止状态。

        将轮次 ID 和 status 追加到 saved，并更新 prepared.terminal；
        不写入真实数据库，也不模拟最终回答字段的持久化。
        """
        self.saved.append((prepared.turn_id, status))
        prepared.terminal = status != "running"
