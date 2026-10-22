"""验证日志环境变量、统一控制台配置和 Web 启动参数。

全局 dictConfig 与 spawn 场景在子进程中运行，避免污染其他测试的日志状态。
"""

import importlib
import os
import subprocess
import sys
from unittest.mock import Mock

import pytest

from app.core.logging import build_logging_config
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
    for name in ("DEEPSEEK_API_KEY", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "POSTGRES_PORT"):
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


def run_isolated(script):
    """在独立解释器执行 script 并返回捕获结果，失败时以 stderr 帮助定位。"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return result


def test_console_format_levels_access_switch_and_repeated_initialization():
    """验证统一格式、分类级别、访问日志开关、重复初始化和输出流分离。"""
    result = run_isolated("""
import logging
from app.core.logging import configure_logging
from app.core.settings import LoggingSettings

# 先模拟 Uvicorn 已安装自己的 handler。
for name in ('uvicorn', 'uvicorn.error', 'uvicorn.access'):
    logging.getLogger(name).addHandler(logging.StreamHandler())
third = logging.getLogger('external.library')
third.setLevel(logging.DEBUG)
settings = LoggingSettings()
configure_logging(settings)
configure_logging(settings)
logging.getLogger('app.agents.agent').debug('hidden-app-debug')
logging.getLogger('app.agents.agent').info('visible-app-info')
logging.getLogger('uvicorn.error').info('visible-server-info')
logging.getLogger('uvicorn.access').info('visible-access-info')
third.info('hidden-third-party-info')
third.warning('visible-third-party-warning')
assert not third.disabled
assert len(logging.getLogger().handlers) == 1
configure_logging(LoggingSettings('DEBUG', 'DEBUG', False))
logging.getLogger('app.agents.agent').debug('visible-app-debug')
third.debug('visible-third-party-debug')
logging.getLogger('uvicorn.access').info('hidden-disabled-access')
print('stdout-reply')
""")
    assert result.stdout.strip() == "stdout-reply"
    lines = result.stderr.splitlines()
    assert len(lines) == 6
    for marker in (
        "visible-app-info", "visible-server-info", "visible-access-info",
        "visible-third-party-warning", "visible-app-debug", "visible-third-party-debug",
    ):
        assert result.stderr.count(marker) == 1
    assert "hidden-" not in result.stderr
    assert "INFO app.agents.agent visible-app-info" in result.stderr
    assert "WARNING external.library visible-third-party-warning" in result.stderr
    assert lines[0][4] == "-" and lines[0][7] == "-"


def test_uvicorn_configuration_is_picklable_and_works_in_spawned_process():
    """验证日志配置可传给 Uvicorn，并能在 spawn 子进程中正常应用。"""
    result = run_isolated("""
import multiprocessing
from app.core.logging import build_logging_config
from app.core.settings import LoggingSettings
from uvicorn import Config

if __name__ == '__main__':
    # 使用标准库函数作为 spawn 目标，以模拟 Windows reload 子进程配置日志。
    config = build_logging_config(LoggingSettings())
    Config('app.main:app', log_config=config)
    import logging
    logging.getLogger('uvicorn.error').info('parent-marker')
    process = multiprocessing.get_context('spawn').Process(
        target=logging.config.dictConfig, args=(config,)
    )
    process.start()
    process.join(10)
    if process.is_alive():
        process.terminate()
        process.join()
        raise AssertionError('spawn did not finish')
    assert process.exitcode == 0
""")
    assert result.stderr.count("INFO uvicorn.error parent-marker") == 1


@pytest.mark.parametrize("argv,expected", [
    ([], {"host": "127.0.0.1", "port": 8000, "reload": False}),
    (["--reload", "--host", "0.0.0.0", "--port", "8080"],
     {"host": "0.0.0.0", "port": 8080, "reload": True}),
])
def test_web_entry_passes_logging_config_and_arguments(monkeypatch, argv, expected):
    """替换服务器启动函数，检查默认或自定义参数和日志字典正确传递。"""
    cli = importlib.import_module("app.__main__")
    settings = LoggingSettings("DEBUG", "ERROR", False)
    monkeypatch.setattr(cli, "load_logging_settings", lambda: settings)
    run = Mock()
    monkeypatch.setattr(cli.uvicorn, "run", run)
    cli.main(argv)
    run.assert_called_once_with(
        "app.main:app", **expected,
        log_config=build_logging_config(settings), access_log=False,
        loop="app.core.event_loop:create_event_loop",
    )


@pytest.mark.parametrize("port", ["0", "65536", "invalid"])
def test_invalid_server_port_is_rejected_before_loading_configuration(monkeypatch, port):
    """验证非法监听端口在读取环境配置和启动服务之前就被拒绝。"""
    cli = importlib.import_module("app.__main__")
    load = Mock()
    monkeypatch.setattr(cli, "load_logging_settings", load)
    with pytest.raises(SystemExit) as error:
        cli.main(["--port", port])
    assert error.value.code == 2
    load.assert_not_called()
