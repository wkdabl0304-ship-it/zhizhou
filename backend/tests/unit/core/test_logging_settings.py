"""日志配置单元测试：临时环境文件隔离真实配置。"""

import os

import pytest

from app.core.settings import LoggingSettings, load_logging_settings

LOG_ENV = ("LOG_LEVEL", "LOG_THIRD_PARTY_LEVEL", "LOG_ACCESS_ENABLED")


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    """清除测试涉及的日志环境变量，返回临时空配置文件避免读取真实 .env。"""
    for name in LOG_ENV:
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / ".env"
    path.write_text("", encoding="utf-8")
    return path


def test_logging_defaults_do_not_require_business_configuration(env_file, monkeypatch):
    """删除业务配置后验证日志默认值可独立加载，且不会修改进程环境。"""
    for name in ("DEEPSEEK_API_KEY", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "POSTGRES_PORT", "POSTGRES_HOST", "JWT_SECRET", "JWT_TTL_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    before = dict(os.environ)
    assert load_logging_settings(env_file) == LoggingSettings()
    assert dict(os.environ) == before


def test_file_settings_and_environment_priority(env_file, monkeypatch):
    """验证文件值先被解析，再由系统环境覆盖，并标准化级别及开关。"""
    env_file.write_text(
        "LOG_LEVEL=debug\nLOG_THIRD_PARTY_LEVEL=error\nLOG_ACCESS_ENABLED=0\n",
        encoding="utf-8",
    )
    assert load_logging_settings(env_file) == LoggingSettings("DEBUG", "ERROR", False)
    monkeypatch.setenv("LOG_LEVEL", "critical")
    monkeypatch.setenv("LOG_THIRD_PARTY_LEVEL", " info ")
    monkeypatch.setenv("LOG_ACCESS_ENABLED", "TRUE")
    assert load_logging_settings(env_file) == LoggingSettings("CRITICAL", "INFO", True)


@pytest.mark.parametrize("name", LOG_ENV)
@pytest.mark.parametrize("value", ["", " \t", "invalid"])
def test_invalid_logging_configuration_names_the_setting(env_file, monkeypatch, name, value):
    """验证空白或非法环境值被拒绝，错误消息能指出对应配置键。"""
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        load_logging_settings(env_file)


@pytest.mark.parametrize("name", ["LOG_LEVEL", "LOG_THIRD_PARTY_LEVEL"])
@pytest.mark.parametrize("value", ["debug", "info", "warning", "error", "critical"])
def test_supported_levels(env_file, monkeypatch, name, value):
    """逐一验证支持的日志级别可忽略大小写读取。"""
    monkeypatch.setenv(name, value)
    settings = load_logging_settings(env_file)
    actual = settings.level if name == "LOG_LEVEL" else settings.third_party_level
    assert actual == value.upper()


@pytest.mark.parametrize("value,enabled", [("true", True), ("FALSE", False), ("1", True), ("0", False)])
def test_supported_access_switches(env_file, monkeypatch, value, enabled):
    """验证文本及数字形式的访问日志开关转换为正确布尔值。"""
    monkeypatch.setenv("LOG_ACCESS_ENABLED", value)
    assert load_logging_settings(env_file).access_enabled is enabled


@pytest.mark.parametrize("name", LOG_ENV)
def test_explicit_empty_file_values_are_invalid(env_file, name):
    """确认文件中的显式空值会报错，而不是悄悄使用默认配置。"""
    env_file.write_text(f"{name}=\n", encoding="utf-8")
    with pytest.raises(ValueError, match=name):
        load_logging_settings(env_file)
