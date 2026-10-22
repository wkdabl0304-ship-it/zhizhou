"""业务数据库资源与版本校验；AsyncSession 由每次短事务独立创建。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config.settings import DatabaseSettings, Settings

SCHEMA_REVISION = "0001_auth_conversations"


def database_url(settings: Settings | DatabaseSettings) -> URL:
    """通过 URL 对象转义凭据，供 ORM 和迁移复用，不把明文连接串写入日志。"""
    return URL.create(
        "postgresql+psycopg",
        username=settings.postgres_user,
        password=settings.postgres_password,
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
    )


@dataclass
class BusinessDatabase:
    """共享引擎及 Session 工厂；锁引擎不复用物理连接，防止会话锁污染连接池。"""

    engine: AsyncEngine
    lock_engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]


async def check_schema(engine: AsyncEngine) -> None:
    """拒绝未迁移或版本不匹配的数据库；不在应用启动时隐式修改业务表。"""
    async with engine.connect() as conn:
        exists = await conn.scalar(text("SELECT to_regclass('alembic_version')"))
        if exists is None:
            raise RuntimeError(
                "业务数据库尚未迁移，请先执行 uv run alembic upgrade head"
            )
        revisions = (
            (await conn.execute(text("SELECT version_num FROM alembic_version")))
            .scalars()
            .all()
        )
        if revisions != [SCHEMA_REVISION]:
            raise RuntimeError(
                "业务数据库版本不匹配，请执行 uv run alembic upgrade head"
            )


@asynccontextmanager
async def open_business_database(settings: Settings) -> AsyncIterator[BusinessDatabase]:
    """创建、校验并释放业务引擎；组装失败也关闭所有已创建连接池。"""
    url = database_url(settings)
    engine = create_async_engine(url, pool_pre_ping=True, hide_parameters=True)
    # advisory lock 持有期间使用自动提交，避免模型生成期间维持长事务。
    lock_engine = create_async_engine(
        url, poolclass=NullPool, isolation_level="AUTOCOMMIT", hide_parameters=True
    )
    try:
        await check_schema(engine)
        yield BusinessDatabase(
            engine, lock_engine, async_sessionmaker(engine, expire_on_commit=False)
        )
    finally:
        await lock_engine.dispose()
        await engine.dispose()
