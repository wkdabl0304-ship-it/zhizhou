"""CLI 集成测试：验证正式命令行入口、异常退出与资源释放。"""

import importlib
import logging
import runpy
from contextlib import asynccontextmanager
from unittest.mock import Mock

import pytest

from app.core.errors.exceptions import BusinessError
from app.core.settings import LoggingSettings
from tests.support.fakes.chat import GraphStub


@pytest.fixture(autouse=True)
def isolate_cli_logging(monkeypatch):
    """保留 pytest 日志捕获，真实全局日志配置由独立进程用例验证。"""
    cli = importlib.import_module("app.agents.__main__")
    monkeypatch.setattr(cli, "load_logging_settings", LoggingSettings)
    monkeypatch.setattr(cli, "configure_logging", Mock())


def test_cli_uses_shared_runtime(monkeypatch, capsys):
    """验证命令行先配置日志，再复用同一组装流程并输出纯文本回复。"""
    cli = importlib.import_module("app.agents.__main__")
    events = []
    graph = GraphStub("CLI reply")
    def business_settings():
        """确认日志已初始化后返回业务配置替身，验证命令行启动顺序。"""
        cli.configure_logging.assert_called_once_with(LoggingSettings())
        return object()

    monkeypatch.setattr(cli, "load_settings", business_settings)
    # 提供模型占位对象，确保本例不构造外部客户端。
    monkeypatch.setattr(cli, "create_model", lambda settings: object())
    # 让正式 CLI 执行本例图替身，观察输入与资源关闭。
    monkeypatch.setattr(cli, "build_agent", lambda model, tools, saver: graph)

    @asynccontextmanager
    async def connection(settings):
        """提供命令行可用的资源替身，并记录退出时关闭连接。"""
        events.append("open")
        try:
            yield object()
        finally:
            events.append("close")

    monkeypatch.setattr(cli, "open_checkpointer", connection)
    cli.main()
    assert capsys.readouterr().out.strip() == "CLI reply"
    assert graph.calls[-1][0]["messages"][0].content == cli.MESSAGE
    assert events == ["open", "close"]


def test_original_module_command_calls_cli(monkeypatch):
    """模拟原模块命令，确认它仍委托到统一的命令行主函数。"""
    cli = importlib.import_module("app.agents.__main__")
    entry = Mock()
    monkeypatch.setattr(cli, "main", entry)
    with pytest.warns(RuntimeWarning, match="found in sys.modules"):
        runpy.run_module("app.agents.agent", run_name="__main__")
    entry.assert_called_once_with()


@pytest.mark.parametrize("failure", [BusinessError(), RuntimeError("private-provider-error")])
def test_cli_application_error_exits_without_duplicate_stack(monkeypatch, capsys, caplog, failure):
    """验证业务和模型失败以退出码 1 结束、释放资源并只记录一次日志。"""
    cli = importlib.import_module("app.agents.__main__")
    graph = GraphStub()
    graph.failure = failure
    # 使用配置占位对象，使异常场景无需真实凭据。
    monkeypatch.setattr(cli, "load_settings", lambda: object())
    # 提供模型占位对象，确保本例不构造外部客户端。
    monkeypatch.setattr(cli, "create_model", lambda settings: object())
    # 让正式 CLI 执行本例图替身，观察输入与资源关闭。
    monkeypatch.setattr(cli, "build_agent", lambda model, tools, saver: graph)
    events = []

    @asynccontextmanager
    async def connection(settings):
        """在失败路径提供保存器替身，并记录 finally 中的资源关闭。"""
        try:
            yield object()
        finally:
            events.append("close")

    monkeypatch.setattr(cli, "open_checkpointer", connection)
    with caplog.at_level(logging.WARNING), pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1
    assert capsys.readouterr().out == ""
    assert events == ["close"]
    records = [record for record in caplog.records if record.name.startswith("app.")]
    assert len(records) == 1
    assert bool(records[0].exc_info) is not isinstance(failure, BusinessError)
