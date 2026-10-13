"""PostgreSQL checkpoint 的连接、初始化与资源释放。"""

from collections.abc import Iterator
from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.conninfo import make_conninfo

from app.config.settings import Settings


def build_conninfo(settings: Settings) -> str:
    """使用驱动转义连接参数，避免特殊字符破坏数据库地址。"""
    return make_conninfo(
        host=settings.postgres_host,
        port=settings.postgres_port,
        user=settings.postgres_user,
        password=settings.postgres_password,
        dbname=settings.postgres_db,
        connect_timeout=10,
    )


@contextmanager
def open_checkpointer(settings: Settings) -> Iterator[PostgresSaver]:
    with PostgresSaver.from_conn_string(build_conninfo(settings)) as checkpointer:
        checkpointer.setup()
        yield checkpointer
