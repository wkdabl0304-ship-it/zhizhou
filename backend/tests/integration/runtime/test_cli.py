"""CLI 集成测试：验证数据库默认模型装配、异常退出与资源释放。"""

import importlib
import logging
import runpy
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.agents.agent import ChatAgent
from app.core.errors.exceptions import BusinessError
from app.core.settings import LoggingSettings
from tests.support.fakes.chat import GraphStub


@pytest.fixture(autouse=True)
def isolate_cli_logging(monkeypatch):
    """保留 pytest 日志捕获，真实全局日志由独立进程验证。"""
    cli = importlib.import_module("app.agents.__main__")
    monkeypatch.setattr(cli, "load_logging_settings", LoggingSettings)
    monkeypatch.setattr(cli, "configure_logging", Mock())


def prepare_cli(monkeypatch, graph, events):
    """只替换数据库与配置来源，保留正式 CLI、事件消费及错误转换。"""
    cli = importlib.import_module("app.agents.__main__")
    snapshot = object()

    def settings():
        """确认日志先初始化，再提供无真实凭据的部署设置。"""
        cli.configure_logging.assert_called_once_with(LoggingSettings())
        return SimpleNamespace(model_config_encryption_key="test-key")

    @asynccontextmanager
    async def database(settings):
        """记录业务数据库进入和退出顺序。"""
        events.append("database-open")
        try:
            yield object()
        finally:
            events.append("database-close")

    @asynccontextmanager
    async def checkpoint(settings):
        """记录保存器在业务数据库关闭前完成回收。"""
        events.append("checkpoint-open")
        try:
            yield object()
        finally:
            events.append("checkpoint-close")

    class Agent:
        """验证 CLI 把数据库取得的快照交给同一执行流程。"""

        def __init__(self, saver, tools):
            """接收正式 CLI 装配的保存器及工具依赖。"""
            assert [tool.name for tool in tools] == ["get_weather"]

        async def achat(self, message, conversation_id, **kwargs):
            """确认快照来源后委托既有 Agent 事件转换。"""
            assert kwargs["snapshot"] is snapshot
            return await ChatAgent(graph).achat(message, conversation_id)

    monkeypatch.setattr(cli, "load_settings", settings)
    monkeypatch.setattr(cli, "open_business_database", database)
    monkeypatch.setattr(cli, "open_checkpointer", checkpoint)
    monkeypatch.setattr(cli, "ModelConfigService", Mock(return_value=Mock(snapshot=AsyncMock(return_value=snapshot))))
    monkeypatch.setattr(cli, "ConfiguredChatAgent", Agent)
    return cli


def test_cli_uses_shared_runtime(monkeypatch, capsys):
    """CLI 读取数据库默认快照，输出纯文本并按逆依赖顺序释放资源。"""
    events = []
    graph = GraphStub("CLI reply")
    cli = prepare_cli(monkeypatch, graph, events)
    cli.main()
    assert capsys.readouterr().out.strip() == "CLI reply"
    assert graph.calls[-1][0]["messages"][0].content == cli.MESSAGE
    assert events == ["database-open", "checkpoint-open", "checkpoint-close", "database-close"]


def test_original_module_command_calls_cli(monkeypatch):
    """原模块命令仍委托统一 CLI 入口。"""
    cli = importlib.import_module("app.agents.__main__")
    entry = Mock()
    monkeypatch.setattr(cli, "main", entry)
    with pytest.warns(RuntimeWarning, match="found in sys.modules"):
        runpy.run_module("app.agents.agent", run_name="__main__")
    entry.assert_called_once_with()


@pytest.mark.parametrize("failure", [BusinessError(), RuntimeError("private-provider-error")])
def test_cli_application_error_exits_without_duplicate_stack(monkeypatch, capsys, caplog, failure):
    """业务或执行失败以状态 1 退出，完成两类数据库清理且只记录一次错误。"""
    graph, events = GraphStub(), []
    graph.failure = failure
    cli = prepare_cli(monkeypatch, graph, events)
    with caplog.at_level(logging.WARNING), pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1 and capsys.readouterr().out == ""
    assert events == ["database-open", "checkpoint-open", "checkpoint-close", "database-close"]
    records = [record for record in caplog.records if record.name.startswith("app.")]
    assert len(records) == 1
    assert bool(records[0].exc_info) is not isinstance(failure, BusinessError)
