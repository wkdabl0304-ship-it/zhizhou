"""Alembic 异步迁移环境，仅比较业务 ORM 元数据，保留 LangGraph 管理的表。"""

import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.config.event_loop import create_event_loop
from app.config.settings import load_database_settings
from app.db.business import database_url
from app.models import Base

target_metadata = Base.metadata


def include_name(name, type_, parent_names):
    """自动生成时只比较已知业务表，不把 checkpoint 等第三方表误判为待删除。"""
    return type_ != "table" or name in target_metadata.tables


def configure_and_run(connection):
    """在异步连接提供的同步桥接中执行 Alembic 的迁移 API。"""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_name=include_name,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_online():
    """通过异步 Psycopg 引擎执行迁移，完成后关闭独立连接。"""
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
