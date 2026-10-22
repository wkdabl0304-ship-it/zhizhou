"""数据库缺失验证脚本：模拟连接不可用，确认默认数据库用例报错而非跳过。"""

from unittest.mock import patch

import pytest


async def unavailable(*args, **kwargs):
    """阻止真实数据库连接，并提供可精确核对的服务不可用原因。"""
    raise RuntimeError("simulated-postgres-unavailable")


with patch("psycopg.AsyncConnection.connect", unavailable):
    raise SystemExit(pytest.main(["-q", "tests/integration/postgres/test_migrations.py"]))
