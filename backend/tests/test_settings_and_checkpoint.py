"""验证业务配置读取、敏感配置隐藏以及 PostgreSQL 资源生命周期。

临时环境文件和保存器替身代替真实凭据、数据库连接及迁移。
"""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace

import pytest
from psycopg.conninfo import conninfo_to_dict

from app.config.settings import Settings, load_database_settings, load_settings
from app.db.checkpoint import build_conninfo, open_checkpointer

ENV_VALUES = {
    "DEEPSEEK_API_KEY": "test-key",
    "JWT_SECRET": "test-jwt-secret-which-is-at-least-32-bytes",
    "POSTGRES_USER": "postgres",
    "POSTGRES_PASSWORD": "test-password",
    "POSTGRES_DB": "zhizhou",
    "POSTGRES_PORT": "5432",
}


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    """清除业务环境覆盖值并写入临时完整配置，供各配置测试独立使用。"""
    for key in ENV_VALUES:
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / ".env"
    path.write_text(
        "\n".join(f"{key}={value}" for key, value in ENV_VALUES.items()),
        encoding="utf-8",
    )
    return path


def test_file_settings_and_environment_priority(env_file, monkeypatch):
    """检查文件配置、默认模型参数、敏感字段隐藏和环境变量优先级。"""
    import os

    before = dict(os.environ)
    settings = load_settings(env_file)
    assert settings.postgres_port == 5432
    assert settings.postgres_host == "127.0.0.1"
    assert settings.model_name == "deepseek-flash"
    assert settings.model_base_url == "https://api.deepseek.com"
    assert dict(os.environ) == before
    assert "test-key" not in repr(settings)
    assert "test-password" not in repr(settings)

    monkeypatch.setenv("DEEPSEEK_API_KEY", "environment-key")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    settings = load_settings(env_file)
    assert settings.deepseek_api_key == "environment-key"
    assert settings.postgres_port == 5433


@pytest.mark.parametrize("key", ENV_VALUES)
@pytest.mark.parametrize("value", ["", " \t"])
def test_required_settings_reject_blank_environment_override(
    env_file, monkeypatch, key, value
):
    """确认空白系统环境即使覆盖有效文件值也会被校验拒绝。"""
    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError, match=key):
        load_settings(env_file)


@pytest.mark.parametrize("port", ["not-a-number", "0", "65536"])
def test_invalid_port_does_not_disclose_value(env_file, monkeypatch, port):
    """验证非整数或越界数据库端口报错，且不直接回显无效原始输入。"""
    monkeypatch.setenv("POSTGRES_PORT", port)
    with pytest.raises(ValueError, match="POSTGRES_PORT") as error:
        load_settings(env_file)
    if port == "not-a-number":
        assert port not in str(error.value)


def test_missing_file_can_use_environment_only(tmp_path, monkeypatch):
    """验证没有 .env 文件时，只通过系统环境仍可加载业务配置。"""
    for key, value in ENV_VALUES.items():
        monkeypatch.setenv(key, value)
    assert load_settings(tmp_path / "missing.env").postgres_db == "zhizhou"


def test_missing_settings_are_named(tmp_path, monkeypatch):
    """验证缺少配置时一次列出必需键名，方便完整补齐。"""
    for key in ENV_VALUES:
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError) as error:
        load_settings(tmp_path / "missing.env")
    assert all(key in str(error.value) for key in ENV_VALUES)


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


@pytest.mark.parametrize("failure", [None, "setup", "body"])
def test_checkpointer_initializes_and_closes_even_on_failure(
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
            asyncio.run(use_connection())
    else:
        asyncio.run(use_connection())
    assert events == (["open", "setup", "close"] if failure == "setup" else [
        "open", "setup", "body", "close"
    ])


@pytest.mark.parametrize("key,value", [
    ("JWT_SECRET", "too-short-secret"),
    ("JWT_TTL_SECONDS", "0"),
    ("JWT_TTL_SECONDS", "-1"),
    ("JWT_TTL_SECONDS", "invalid"),
    ("JWT_TTL_SECONDS", ""),
    ("POSTGRES_HOST", ""),
    ("POSTGRES_HOST", "  "),
])
def test_auth_settings_and_host_validation_hide_invalid_values(env_file, monkeypatch, key, value):
    """拒绝弱长度密钥、无效令牌寿命和空主机，错误只指出配置键而不回显原值。"""
    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError, match=key) as error:
        load_settings(env_file)
    if value in {"too-short-secret", "invalid"}:
        assert value not in str(error.value)


def test_migration_configuration_needs_only_database_values(tmp_path, monkeypatch):
    """迁移加载与模型/JWT 解耦，避免首次部署必须先准备无关应用凭据。"""
    for key in ENV_VALUES:
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / ".env"
    path.write_text("\n".join(f"{key}={value}" for key, value in ENV_VALUES.items() if key.startswith("POSTGRES_")), encoding="utf-8")
    settings = load_database_settings(path)
    assert settings.postgres_db == "zhizhou" and settings.postgres_host == "127.0.0.1"
