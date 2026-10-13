import importlib
import os
import subprocess
import sys
from unittest.mock import Mock

import pytest

from app.config.logging import build_logging_config
from app.config.settings import LoggingSettings, load_logging_settings

LOG_ENV = ("LOG_LEVEL", "LOG_THIRD_PARTY_LEVEL", "LOG_ACCESS_ENABLED")


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    for name in LOG_ENV:
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / ".env"
    path.write_text("", encoding="utf-8")
    return path


def test_logging_defaults_do_not_require_business_configuration(env_file, monkeypatch):
    for name in ("DEEPSEEK_API_KEY", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "POSTGRES_PORT"):
        monkeypatch.delenv(name, raising=False)
    before = dict(os.environ)
    assert load_logging_settings(env_file) == LoggingSettings()
    assert dict(os.environ) == before


def test_file_settings_and_environment_priority(env_file, monkeypatch):
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
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        load_logging_settings(env_file)


@pytest.mark.parametrize("name", ["LOG_LEVEL", "LOG_THIRD_PARTY_LEVEL"])
@pytest.mark.parametrize("value", ["debug", "info", "warning", "error", "critical"])
def test_supported_levels(env_file, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    settings = load_logging_settings(env_file)
    actual = settings.level if name == "LOG_LEVEL" else settings.third_party_level
    assert actual == value.upper()


@pytest.mark.parametrize("value,enabled", [("true", True), ("FALSE", False), ("1", True), ("0", False)])
def test_supported_access_switches(env_file, monkeypatch, value, enabled):
    monkeypatch.setenv("LOG_ACCESS_ENABLED", value)
    assert load_logging_settings(env_file).access_enabled is enabled


@pytest.mark.parametrize("name", LOG_ENV)
def test_explicit_empty_file_values_are_invalid(env_file, name):
    env_file.write_text(f"{name}=\n", encoding="utf-8")
    with pytest.raises(ValueError, match=name):
        load_logging_settings(env_file)


def run_isolated(script):
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return result


def test_console_format_levels_access_switch_and_repeated_initialization():
    result = run_isolated("""
import logging
from app.config.logging import configure_logging
from app.config.settings import LoggingSettings

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
    result = run_isolated("""
import multiprocessing
from app.config.logging import build_logging_config
from app.config.settings import LoggingSettings
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
    cli = importlib.import_module("app.__main__")
    settings = LoggingSettings("DEBUG", "ERROR", False)
    monkeypatch.setattr(cli, "load_logging_settings", lambda: settings)
    run = Mock()
    monkeypatch.setattr(cli.uvicorn, "run", run)
    cli.main(argv)
    run.assert_called_once_with(
        "app.main:app", **expected,
        log_config=build_logging_config(settings), access_log=False,
    )


@pytest.mark.parametrize("port", ["0", "65536", "invalid"])
def test_invalid_server_port_is_rejected_before_loading_configuration(monkeypatch, port):
    cli = importlib.import_module("app.__main__")
    load = Mock()
    monkeypatch.setattr(cli, "load_logging_settings", load)
    with pytest.raises(SystemExit) as error:
        cli.main(["--port", port])
    assert error.value.code == 2
    load.assert_not_called()
