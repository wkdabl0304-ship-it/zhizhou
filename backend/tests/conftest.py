"""测试公共资源：显式启用 PostgreSQL 集成测试时创建并销毁独立随机数据库。

默认单元测试不连接外部服务；ZHIZHOU_TEST_POSTGRES=1 时从现有数据库配置
取得连接，只对本 fixture 成功创建且带随机名称的测试库执行清理。
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from app.config.event_loop import create_event_loop
from app.config.settings import Settings, load_database_settings
from app.db.checkpoint import build_conninfo


def run_async(coroutine):
    """每个测试使用新的兼容 Psycopg 的事件循环，防止跨循环复用异步连接。"""
    with asyncio.Runner(loop_factory=create_event_loop) as runner:
        return runner.run(coroutine)


@pytest.fixture(scope="session")
def postgres_settings():
    """显式启用时创建隔离库并运行正式迁移，结束后仅删除本 fixture 创建的库。"""
    if os.environ.get("ZHIZHOU_TEST_POSTGRES") != "1":
        pytest.skip("设置 ZHIZHOU_TEST_POSTGRES=1 后运行独立 PostgreSQL 集成测试")
    base = load_database_settings()
    database_name = f"zhizhou_test_{uuid4().hex}"

    async def database_command(action):
        """用驱动标识符转义执行隔离库的创建和回收，不拼接凭据或任意目标。"""
        async with await psycopg.AsyncConnection.connect(
            build_conninfo(base), autocommit=True
        ) as connection:
            if action == "create":
                await connection.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name))
                )
            else:
                assert (
                    database_name.startswith("zhizhou_test_")
                    and len(database_name) == 45
                )
                await connection.execute(
                    sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                        sql.Identifier(database_name)
                    )
                )

    run_async(database_command("create"))
    settings = Settings(
        deepseek_api_key="unused-test-key",
        postgres_user=base.postgres_user,
        postgres_password=base.postgres_password,
        postgres_db=database_name,
        postgres_port=base.postgres_port,
        postgres_host=base.postgres_host,
        jwt_secret="integration-secret-which-is-at-least-48-bytes-long-for-tests",
    )
    try:
        env = {**os.environ, "POSTGRES_DB": database_name, "PYTHONIOENCODING": "utf-8"}
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        yield settings
    finally:
        run_async(database_command("drop"))
