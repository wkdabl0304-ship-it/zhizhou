"""测试收集验证脚本：禁止驱动连接，确认收集阶段不需要数据库或业务密钥。"""

from unittest.mock import patch

import pytest


def forbidden(*args, **kwargs):
    """让任何意外数据库连接立即暴露为测试收集错误。"""
    raise AssertionError("测试收集不应连接 PostgreSQL")

with (
    patch("psycopg.AsyncConnection.connect", forbidden),
    patch("psycopg.Connection.connect", forbidden),
):
    raise SystemExit(pytest.main(["--collect-only", "-q"]))
