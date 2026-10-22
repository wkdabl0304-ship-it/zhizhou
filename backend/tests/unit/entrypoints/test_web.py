"""Web 入口单元测试：替换服务器启动函数验证参数和日志配置。"""

import importlib
from unittest.mock import Mock

import pytest

from app.core.logging import build_logging_config
from app.core.settings import LoggingSettings


@pytest.mark.parametrize("argv,expected", [
    ([], {"host": "127.0.0.1", "port": 8000, "reload": False}),
    (["--reload", "--host", "0.0.0.0", "--port", "8080"],
     {"host": "0.0.0.0", "port": 8080, "reload": True}),
])
def test_web_entry_passes_logging_config_and_arguments(monkeypatch, argv, expected):
    """替换服务器启动函数，检查默认或自定义参数和日志字典正确传递。"""
    cli = importlib.import_module("app.__main__")
    settings = LoggingSettings("DEBUG", "ERROR", False)
    # 返回本例日志配置，让入口参数断言不依赖真实 .env。
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
