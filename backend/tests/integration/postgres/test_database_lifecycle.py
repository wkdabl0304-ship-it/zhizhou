"""临时库真实集成回归：验证用例异常和迁移异常后实际数据库已被回收。"""

from dataclasses import replace

import psycopg
import pytest

from app.core.settings import load_database_settings
from app.db.checkpoint import build_conninfo
from tests.support import postgres

pytestmark = [pytest.mark.postgres, pytest.mark.anyio]


async def assert_removed(base, name):
    """从维护库查询临时库是否存在，验证实际清理结果而非仅检查函数调用。"""
    async with await psycopg.AsyncConnection.connect(
        build_conninfo(replace(base, postgres_db="postgres")), autocommit=True,
        connect_timeout=5,
    ) as connection:
        cursor = await connection.execute("SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = %s)", (name,))
        row = await cursor.fetchone()
        assert row == (False,)


async def test_test_failure_removes_actual_temporary_database():
    """验证用例在获得已迁移库之后抛出异常，最终仍实际销毁本例数据库。"""
    base = load_database_settings()
    with pytest.raises(RuntimeError, match="模拟用例失败"):
        async with postgres.temporary_database(base) as settings:
            name = settings.postgres_db
            raise RuntimeError("模拟用例失败")
    await assert_removed(base, name)


async def test_migration_failure_removes_actual_temporary_database(monkeypatch):
    """验证库创建成功但迁移失败时不会遗留真实临时库。"""
    base = load_database_settings()
    targets = []

    def fail_migration(settings):
        """记录真实建库目标并中止迁移，模拟初始化阶段异常。"""
        targets.append(settings.postgres_db)
        raise RuntimeError("模拟迁移失败")

    monkeypatch.setattr(postgres, "migrate_database", fail_migration)
    with pytest.raises(RuntimeError, match="模拟迁移失败"):
        async with postgres.temporary_database(base):
            pytest.fail("迁移失败时不应开放运行环境")
    await assert_removed(base, targets[0])
