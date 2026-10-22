"""配置单元测试：验证业务配置的读取、校验与迁移配置解耦。"""

import pytest

from app.core.settings import load_database_settings, load_settings

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
    for key in (*ENV_VALUES, "POSTGRES_HOST", "JWT_TTL_SECONDS"):
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
    for key in (*ENV_VALUES, "POSTGRES_HOST", "JWT_TTL_SECONDS"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError) as error:
        load_settings(tmp_path / "missing.env")
    assert all(key in str(error.value) for key in ENV_VALUES)


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
    for key in (*ENV_VALUES, "POSTGRES_HOST", "JWT_TTL_SECONDS"):
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / ".env"
    path.write_text("\n".join(f"{key}={value}" for key, value in ENV_VALUES.items() if key.startswith("POSTGRES_")), encoding="utf-8")
    settings = load_database_settings(path)
    assert settings.postgres_db == "zhizhou" and settings.postgres_host == "127.0.0.1"
