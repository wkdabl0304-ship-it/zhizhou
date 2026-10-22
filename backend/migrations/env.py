"""Alembic 异步迁移环境，仅比较业务 ORM 元数据，保留 LangGraph 管理的表。"""

import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.event_loop import create_event_loop
from app.core.settings import load_database_settings
from app.db.business import database_url
from app.models import Base

target_metadata = Base.metadata


def include_name(name, type_, parent_names):
    """筛选 Alembic 自动比较结构时允许检查的数据库对象。

    对表名只接受业务 ORM 元数据中已有的条目，其他类型的对象正常比较；
    返回布尔值给 Alembic，避免将 checkpoint 等第三方表误判为待删除。
    """
    return type_ != "table" or name in target_metadata.tables


def configure_and_run(connection):
    """配置并执行当前数据库连接上的业务迁移。

    connection 由异步引擎的 run_sync 提供；绑定业务元数据和对象过滤器后，
    在迁移事务中执行升级或检查等 Alembic 操作。
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_name=include_name,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_online():
    """连接数据库并运行在线迁移，供 Alembic 命令使用。

    只加载数据库配置，创建不复用连接的异步引擎；连接后通过同步桥接
    调用 configure_and_run，成功或失败都在 finally 中释放引擎。
    """
    engine = create_async_engine(
        database_url(load_database_settings()), poolclass=NullPool, hide_parameters=True
    )
    try:
        async with engine.connect() as connection:
            await connection.run_sync(configure_and_run)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    context.configure(
        url=database_url(load_database_settings()),
        target_metadata=target_metadata,
        literal_binds=True,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    with asyncio.Runner(loop_factory=create_event_loop) as runner:
        runner.run(run_online())
