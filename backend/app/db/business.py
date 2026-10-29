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

from app.core.settings import DatabaseSettings, Settings

SCHEMA_REVISION = "0007_file_spaces"


def database_url(settings: Settings | DatabaseSettings) -> URL:
    """构造业务数据库的 SQLAlchemy 连接地址，供 ORM 和迁移复用。

    从 settings 读取 PostgreSQL 配置并交给 URL 对象处理凭据转义，
    返回地址对象但不连接数据库；调用方不应把含明文凭据的地址写入日志。
    """
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


@asynccontextmanager
async def session_scope(database: BusinessDatabase, session: AsyncSession | None = None, *,
                        write: bool = False) -> AsyncIterator[AsyncSession]:
    """复用调用者事务或创建独立短会话，避免授权包装层持连接时再次申请连接。

    传入 session 时必须已有事务，提交、回滚及关闭均由调用者负责；否则写操作
    创建 begin 上下文，读操作只创建会话。借用事务的异常原样传播给外层回滚。
    """
    if session is not None:
        if not session.in_transaction():
            raise ValueError("复用的业务 Session 必须处于调用者事务中")
        yield session
        return
    context = database.sessions.begin() if write else database.sessions()
    async with context as opened:
        yield opened


async def check_schema(engine: AsyncEngine) -> None:
    """检查业务数据库是否已经迁移到当前代码要求的版本。

    通过 engine 读取 Alembic 版本表；表不存在或版本与 SCHEMA_REVISION
    不符时抛出 RuntimeError，提示先运行迁移。检查只读取版本，不修改业务表。
    """
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
    """在应用生命周期内提供业务数据库资源，并在退出时释放连接。

    按 settings 创建业务引擎、专用锁引擎和 Session 工厂，版本检查通过后
    yield BusinessDatabase。模型执行期间锁连接使用自动提交，避免长事务；
    正常退出或初始化失败都会进入 finally，依次释放两个引擎。
    """
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
