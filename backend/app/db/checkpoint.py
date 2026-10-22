"""管理 PostgreSQL checkpoint 的连接参数、表初始化和连接生命周期。

此模块提供持久化基础设施；对话消息与 conversation_id 的处理仍由 Agent 负责。
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.conninfo import make_conninfo

from app.core.settings import Settings


def build_conninfo(settings: Settings) -> str:
    """构造 checkpoint 保存器连接 PostgreSQL 所需的驱动连接字符串。

    参数从 settings 取得，构造过程不发起数据库连接。
    使用驱动转义用户名、密码等参数，支持空格、引号和地址特殊字符。
    连接超时为 10 秒；返回值包含凭据，调用方不应将其写入日志。
    """
    return make_conninfo(
        host=settings.postgres_host,
        port=settings.postgres_port,
        user=settings.postgres_user,
        password=settings.postgres_password,
        dbname=settings.postgres_db,
        connect_timeout=10,
    )


@asynccontextmanager
async def open_checkpointer(settings: Settings) -> AsyncIterator[AsyncPostgresSaver]:
    """为 Agent 提供可持久化对话状态的 PostgreSQL checkpoint 保存器。

    进入时根据 settings 连接数据库并执行可重复的 setup 迁移；yield
    出的保存器必须在 async with 范围内使用。正常退出或发生异常都会关闭连接。
    连接或迁移失败会向调用方抛出，不降级为没有记忆的临时 Agent。
    """
    async with AsyncPostgresSaver.from_conn_string(build_conninfo(settings)) as checkpointer:
        await checkpointer.setup()
        yield checkpointer
