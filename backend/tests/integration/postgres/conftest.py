"""PostgreSQL 专属资源：每例创建、迁移和删除独立随机库，默认执行且不跳过。"""

import pytest

from app.core.settings import load_database_settings
from tests.support.postgres import temporary_database


@pytest.fixture
async def postgres_settings(anyio_backend):
    """提供本例临时库配置，所有业务资源退出后再销毁数据库。"""
    async with temporary_database(load_database_settings()) as settings:
        yield settings
