"""临时测试库支撑回归：用驱动替身验证目标保护、失败清理与完整迁移配置。"""

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from psycopg.conninfo import conninfo_to_dict

from app.core.settings import DatabaseSettings
from tests.support import postgres


@pytest.fixture
def driver(monkeypatch):
    """提供只记录维护连接和 DDL 的驱动替身，不访问任何真实数据库。"""
    state = SimpleNamespace(connections=[], statements=[], reject_create=False)

    async def execute(statement):
        """记录数据库命令，并按场景模拟建库权限不足。"""
        command = statement.as_string()
        state.statements.append(command)
        if state.reject_create and command.startswith("CREATE"):
            raise RuntimeError("create denied")

    @asynccontextmanager
    async def connection():
        """提供仅含 execute 的维护连接，由上下文自动退出。"""
        yield SimpleNamespace(execute=execute)

    async def connect(conninfo, **kwargs):
        """记录维护目标并返回异步连接上下文，避免泄露或使用真实配置。"""
        state.connections.append(conninfo_to_dict(conninfo))
        return connection()

    monkeypatch.setattr(postgres.psycopg.AsyncConnection, "connect", connect)
    return state


@pytest.fixture
def base():
    """提供虚构开发库配置，验证维护操作不会使用它作为清理目标。"""
    return DatabaseSettings("test-user", "test-password", "development", 5432)


@pytest.mark.anyio
async def test_only_owned_database_is_dropped_once(driver, base):
    """验证维护连接固定使用 postgres，清理仅针对成功创建的库且可重复调用。"""
    database = postgres.TemporaryDatabase(base)
    settings = await database.create()
    assert settings.postgres_db == database.name != base.postgres_db
    assert settings.file_storage_root.is_dir()
    assert settings.file_storage_root.name.startswith("zhizhou-test-files-")
    # 原件目录随本次成功创建的精确目标库一并回收，不依赖开发磁盘路径。
    (settings.file_storage_root / "test-original").write_bytes(b"test-only")
    await database.drop()
    await database.drop()
    assert not settings.file_storage_root.exists()
    assert driver.statements == [
        f'CREATE DATABASE "{database.name}"',
        f'DROP DATABASE "{database.name}" WITH (FORCE)',
    ]
    assert all(connection["dbname"] == "postgres" for connection in driver.connections)


@pytest.mark.anyio
async def test_failed_create_does_not_authorize_drop(driver, base):
    """验证建库失败不会登记清理权限，也不会删除名称碰巧相同的已有库。"""
    driver.reject_create = True
    database = postgres.TemporaryDatabase(base)
    with pytest.raises(RuntimeError, match="create denied"):
        await database.create()
    await database.drop()
    assert len(driver.statements) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("foreign", ["development", "zhizhou_test_" + "a" * 32])
async def test_name_prefix_alone_never_authorizes_cleanup(driver, base, foreign):
    """验证开发库或其他合法前缀库都无法替代本次登记的精确清理目标。"""
    database = postgres.TemporaryDatabase(base)
    await database.create()
    owned = database.name
    database.name = foreign
    with pytest.raises(RuntimeError, match="拒绝清理"):
        await database.drop()
    assert len(driver.statements) == 1
    database.name = owned
    await database.drop()


@pytest.mark.anyio
@pytest.mark.parametrize("failure", [None, "migration", "body"])
async def test_lifecycle_cleans_after_migration_or_test_failure(driver, base, monkeypatch, failure):
    """验证迁移失败和用例失败均回收已创建库，失败不会被转换为跳过。"""
    migrated = []
    announced = []

    def migrate(settings):
        """记录迁移目标并可模拟正式迁移失败，在线程中执行但不启动子进程。"""
        migrated.append(settings.postgres_db)
        assert announced == [settings.postgres_db]
        if failure == "migration":
            raise RuntimeError("migration failed")

    monkeypatch.setattr(postgres, "migrate_database", migrate)
    if failure:
        with pytest.raises(RuntimeError, match=f"{failure} failed"):
            async with postgres.temporary_database(base, on_created=announced.append):
                raise RuntimeError("body failed")
    else:
        async with postgres.temporary_database(base, on_created=announced.append) as settings:
            assert settings.postgres_db == migrated[0]
    assert driver.statements[0].startswith("CREATE DATABASE")
    assert driver.statements[-1].startswith("DROP DATABASE")
    assert len(driver.statements) == 2


@pytest.mark.anyio
async def test_created_notification_failure_still_drops_owned_database(driver, base):
    """日志通知失败也回收已创建的库，避免迁移之前发生的异常泄漏资源。"""
    def broken_notice(name):
        """模拟调用方输出失效，不读取数据库凭据或执行后续迁移。"""
        raise RuntimeError("notice failed")

    with pytest.raises(RuntimeError, match="notice failed"):
        async with postgres.temporary_database(base, on_created=broken_notice):
            pytest.fail("通知失败后不应进入用例")
    assert len(driver.statements) == 2
    assert driver.statements[-1].startswith("DROP DATABASE")


def test_migration_overrides_every_database_setting(base, monkeypatch):
    """验证迁移子进程使用完整目标配置，不继承父进程的开发库地址或账号。"""
    calls = []

    def run(*arguments, **kwargs):
        """截取解释器参数和环境覆盖值，隔离真实迁移子进程。"""
        calls.append((arguments, kwargs))

    monkeypatch.setattr(postgres, "run_python", run)
    postgres.migrate_database(base)
    assert calls == [
        (("-m", "alembic", "upgrade", "head"), {"env_overrides": {
            "POSTGRES_HOST": "127.0.0.1", "POSTGRES_PORT": "5432",
            "POSTGRES_USER": "test-user", "POSTGRES_PASSWORD": "test-password",
            "POSTGRES_DB": "development",
        }}),
    ]
