"""checkpoint 单元测试：通过保存器替身验证连接转义及资源释放。"""

from contextlib import asynccontextmanager
from dataclasses import replace

import pytest
from psycopg.conninfo import conninfo_to_dict

from app.core.settings import Settings
from app.db.checkpoint import build_conninfo, open_checkpointer


@pytest.fixture
def settings():
    """提供数据库测试用的配置对象，所有凭据仅为无网络用途的测试值。"""
    return Settings("key", "postgres", "password", "zhizhou", 5432)


def test_connection_parameters_preserve_special_characters(settings):
    """检查用户名、库名和密码中的特殊字符经驱动转义后仍可原样解析。"""
    password = " p@ss:/?#='\\ word "
    settings = replace(
        settings, postgres_password=password, postgres_user="user name", postgres_db="db'name"
    )
    values = conninfo_to_dict(build_conninfo(settings))
    assert values["password"] == password
    assert values["user"] == "user name"
    assert values["dbname"] == "db'name"
    assert values["port"] == "5432"


@pytest.mark.anyio
@pytest.mark.parametrize("failure", [None, "setup", "body"])
async def test_checkpointer_initializes_and_closes_even_on_failure(
    settings, monkeypatch, failure
):
    """分别模拟正常使用、迁移失败和上下文内部失败，检查生命周期顺序。"""
    from app.db import checkpoint

    events = []

    class Saver:
        """仅模拟异步 setup 的保存器，用于观察迁移异常及上下文清理顺序。"""

        async def setup(self):
            """记录初始化事件，并根据测试参数模拟迁移失败。"""
            events.append("setup")
            if failure == "setup":
                raise RuntimeError("setup failed")

    saver = Saver()

    @asynccontextmanager
    async def connection(conninfo):
        """检查连接参数，提供保存器替身，并保证 finally 记录关闭事件。"""
        assert conninfo_to_dict(conninfo)["dbname"] == "zhizhou"
        events.append("open")
        try:
            yield saver
        finally:
            events.append("close")

    monkeypatch.setattr(checkpoint.AsyncPostgresSaver, "from_conn_string", connection)

    async def use_connection():
        """执行受测资源上下文，并按参数模拟业务使用期间的异常。"""
        async with open_checkpointer(settings) as actual:
            assert actual is saver
            events.append("body")
            if failure == "body":
                raise RuntimeError("body failed")

    if failure:
        with pytest.raises(RuntimeError, match=f"{failure} failed"):
            await use_connection()
    else:
        await use_connection()
    assert events == (["open", "setup", "close"] if failure == "setup" else [
        "open", "setup", "body", "close"
    ])
