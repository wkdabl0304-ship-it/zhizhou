"""默认数据库要求集成回归：不连接真实服务，验证 fixture 初始化失败的退出语义。"""

import pytest

from tests.support.processes import SCRIPTS, run_python


@pytest.mark.subprocess
def test_unavailable_database_fails_instead_of_skipping():
    """验证 PostgreSQL 连接失败导致测试进程失败，不会输出成功或自动跳过。"""
    result = run_python(
        str(SCRIPTS / "database_unavailable.py"),
        env_overrides={
            "POSTGRES_HOST": "127.0.0.1", "POSTGRES_PORT": "5432",
            "POSTGRES_USER": "test-user", "POSTGRES_PASSWORD": "test-password",
            "POSTGRES_DB": "development",
        },
        expected_returncode=1,
    )
    assert "simulated-postgres-unavailable" in result.stdout
    assert "1 error" in result.stdout
    assert "skipped" not in result.stdout
