"""验证聊天 HTTP 接口、生命周期、统一响应和命令行兼容入口。

将外部资源替换为测试对象，并隔离日志初始化，保留 pytest 的日志捕获。
"""

import importlib
import logging
import os
import runpy
import subprocess
import sys
from contextlib import contextmanager
from unittest.mock import Mock

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.config.settings import LoggingSettings
from app.api.dependencies import get_chat_agent
from app.errors.codes import ErrorCode
from app.errors.exceptions import BusinessError

main = importlib.import_module("app.main")


@pytest.fixture(autouse=True)
def isolate_logging_configuration(monkeypatch):
    # 全局 dictConfig 在独立子进程中测试；这里保留 pytest 的 caplog handler。
    """为每个测试替换全局日志初始化，避免清除 pytest 的 caplog handler。"""
    cli = importlib.import_module("app.agents.__main__")
    for module in (main, cli):
        monkeypatch.setattr(module, "load_logging_settings", lambda: LoggingSettings())
        monkeypatch.setattr(module, "configure_logging", Mock())


@pytest.fixture
def runtime(monkeypatch):
    """返回 Agent 图替身与生命周期事件列表，并替换模型、配置和数据库依赖。"""
    events = []
    graph = Mock()
    graph.invoke.return_value = {"messages": [AIMessage(content="你好") ]}
    settings = object()
    model = object()
    saver = object()
    monkeypatch.setattr(main, "load_settings", lambda: settings)
    monkeypatch.setattr(main, "create_model", lambda actual: model if actual is settings else None)

    @contextmanager
    def open_checkpointer(actual):
        """模拟数据库上下文，校验注入配置并记录打开和关闭事件。"""
        assert actual is settings
        events.append("open")
        try:
            yield saver
        finally:
            events.append("close")

    def build_agent(actual_model, tools, actual_saver):
        """确认启动流程传入正确模型、工具与保存器，再返回图替身。"""
        assert actual_model is model
        assert actual_saver is saver
        assert [tool.name for tool in tools] == ["get_weather"]
        events.append("build")
        return graph

    monkeypatch.setattr(main, "open_checkpointer", open_checkpointer)
    monkeypatch.setattr(main, "build_agent", build_agent)
    return graph, events


def test_chat_and_lifespan(runtime, caplog):
    """验证多次 HTTP 调用共用启动资源、返回统一成功响应并在退出时清理。"""
    graph, events = runtime
    with caplog.at_level(logging.INFO, logger="app.main"), TestClient(main.app) as client:
        assert events == ["open", "build"]
        for thread in ["conversation-001", "conversation-001", "other"]:
            response = client.post("/api/chat", json={"message": "你好", "thread_id": thread})
            assert response.status_code == 200
            assert response.json() == {
                "code": 0, "message": "成功", "data": {"reply": "你好", "thread_id": thread},
            }
            assert type(response.json()["code"]) is int
            assert graph.invoke.call_args.kwargs["config"]["configurable"]["thread_id"] == thread
        assert events == ["open", "build"]
        assert client.get("/docs").status_code == 200
    assert events == ["open", "build", "close"]
    assert not hasattr(main.app.state, "chat_agent")
    assert [record.getMessage() for record in caplog.records if record.name == "app.main"] == [
        "应用启动完成", "应用资源已关闭",
    ]
    main.configure_logging.assert_called_once_with(LoggingSettings())


@pytest.mark.parametrize("body", [
    {}, {"message": "hi"}, {"thread_id": "a"},
    {"message": "", "thread_id": "a"},
    {"message": " \n\t", "thread_id": "a"},
    {"message": "hi", "thread_id": ""},
    {"message": "hi", "thread_id": " \t"},
    {"message": None, "thread_id": "a"},
    {"message": "hi", "thread_id": 123},
])
def test_invalid_request_does_not_invoke_agent(runtime, body):
    """验证各类非法字段返回统一 422，并在进入 Agent 之前被拒绝。"""
    graph, _ = runtime
    with TestClient(main.app) as client:
        response = client.post("/api/chat", json=body)
        assert response.status_code == 422
        assert response.json() == {"code": 42200, "message": "请求参数校验失败", "data": None}
    graph.invoke.assert_not_called()


def test_model_error_returns_generic_error_and_logs_details(runtime, caplog):
    """验证模型失败返回安全的系统响应，底层细节只进入一次服务端日志。"""
    graph, _ = runtime
    graph.invoke.side_effect = RuntimeError("private-provider-error")
    with TestClient(main.app) as client, caplog.at_level(logging.ERROR):
        response = client.post("/api/chat", json={"message": "hi", "thread_id": "a"})
    assert response.status_code == 500
    assert response.json() == {"code": 50001, "message": "对话执行失败，请稍后重试", "data": None}
    assert "private-provider-error" not in response.text
    assert "private-provider-error" in caplog.text
    failures = [record for record in caplog.records if record.exc_info]
    assert len(failures) == 1
    assert failures[0].name == "app.agents.agent"
    assert failures[0].thread_id == "a"


def test_business_error_from_agent_is_http_200_with_catalog_message(runtime, caplog):
    """验证 Agent 业务异常保留数字码和中央解释，使用 HTTP 200 且无堆栈。"""
    graph, _ = runtime
    error = BusinessError(ErrorCode.BUSINESS_ERROR)
    graph.invoke.side_effect = error
    with caplog.at_level(logging.WARNING), TestClient(main.app) as client:
        response = client.post("/api/chat", json={"message": "private-request", "thread_id": "a"})
    assert response.status_code == 200
    assert response.json() == {"code": 20000, "message": "业务处理失败", "data": None}
    records = [record for record in caplog.records if record.name.startswith("app.")]
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert not records[0].exc_info
    assert error.logged


def test_invalid_json_is_uniform_422_and_not_sent_to_agent(runtime):
    """验证无法解析的 JSON 返回统一 422，且不泄露输入或调用模型。"""
    graph, _ = runtime
    with TestClient(main.app) as client:
        response = client.post("/api/chat", content='{"private-input":', headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json() == {"code": 42200, "message": "请求参数校验失败", "data": None}
    assert "private-input" not in response.text
    graph.invoke.assert_not_called()


def test_openapi_documents_typed_envelope_business_failure_and_uniform_errors(runtime):
    """检查 OpenAPI 保留聊天数据类型、业务失败示例和统一错误模型。"""
    with TestClient(main.app) as client:
        schema = client.get("/openapi.json").json()
    assert "openapi" in schema and "code" not in schema
    assert "/chat" not in schema["paths"]
    assert "/api/api/chat" not in schema["paths"]
    assert schema["paths"]["/api/chat"]["post"]["tags"] == ["聊天"]
    responses = schema["paths"]["/api/chat"]["post"]["responses"]
    content = responses["200"]["content"]["application/json"]
    assert "code=0" in responses["200"]["description"]
    assert content["examples"]["business_error"]["value"]["code"] == 20000
    envelope = schema["components"]["schemas"][content["schema"]["$ref"].split("/")[-1]]
    assert envelope["properties"]["code"]["type"] == "integer"
    assert any(item.get("$ref", "").endswith("/ChatResponse") for item in envelope["properties"]["data"]["anyOf"])
    for status in ("404", "405", "422", "500"):
        reference = responses[status]["content"]["application/json"]["schema"]["$ref"]
        error_schema = schema["components"]["schemas"][reference.split("/")[-1]]
        assert set(error_schema["properties"]) == {"code", "message", "data"}
        assert error_schema["properties"]["data"]["type"] == "null"
    assert "HTTPValidationError" not in schema["components"]["schemas"]


@pytest.mark.parametrize("method,path,status,code", [
    ("POST", "/chat", 404, 40400),
    ("GET", "/api/chat", 405, 40500),
])
def test_chat_migration_rejects_old_path_and_wrong_method(runtime, method, path, status, code):
    """确认旧路径已移除，新路径只接受 POST，并继续使用统一协议错误响应。"""
    graph, _ = runtime
    with TestClient(main.app) as client:
        response = client.request(method, path, json={"message": "你好", "thread_id": "a"})
    assert response.status_code == status
    assert response.json()["code"] == code
    assert response.json()["data"] is None
    if status == 405:
        assert "POST" in response.headers["allow"]
    graph.invoke.assert_not_called()


def test_chat_dependency_reuses_initialized_agent(runtime, monkeypatch):
    """观察真实请求的依赖解析，确认多轮调用复用已初始化的 Agent 和连接。"""
    graph, events = runtime
    observed = []

    def observe_agent(request: Request):
        """委托真实依赖并记录其结果，用于检查请求间是否复用同一资源。"""
        agent = get_chat_agent(request)
        observed.append(agent)
        return agent

    monkeypatch.setitem(main.app.dependency_overrides, get_chat_agent, observe_agent)
    with TestClient(main.app) as client:
        initialized_agent = main.app.state.chat_agent
        for message in ("第一轮", "第二轮"):
            response = client.post("/api/chat", json={"message": message, "thread_id": "a"})
            assert response.status_code == 200
        assert observed == [initialized_agent, initialized_agent]
        assert events == ["open", "build"]
    assert graph.invoke.call_count == 2
    assert events == ["open", "build", "close"]


def test_chat_dependency_can_be_overridden(runtime, monkeypatch):
    """验证接口通过公共依赖取得 Agent，测试替身可替换它而不执行原图。"""
    graph, _ = runtime
    replacement = Mock()
    replacement.chat.return_value = "依赖替身回复"

    def override_agent():
        """为请求返回独立的 Agent 替身，不读取或重建应用资源。"""
        return replacement

    monkeypatch.setitem(main.app.dependency_overrides, get_chat_agent, override_agent)
    with TestClient(main.app) as client:
        response = client.post("/api/chat", json={"message": "你好", "thread_id": "override"})
    assert response.status_code == 200
    assert response.json() == {
        "code": 0, "message": "成功",
        "data": {"reply": "依赖替身回复", "thread_id": "override"},
    }
    replacement.chat.assert_called_once_with("你好", "override")
    graph.invoke.assert_not_called()


def test_configuration_error_aborts_startup(monkeypatch, caplog):
    """验证先初始化日志，再加载业务配置，配置失败时不连接数据库。"""
    def fail_configuration():
        """确认日志已准备好后模拟缺少业务配置，使测试覆盖启动失败路径。"""
        main.configure_logging.assert_called_once_with(LoggingSettings())
        raise ValueError("missing configuration")

    loader = Mock(side_effect=fail_configuration)
    database = Mock()
    monkeypatch.setattr(main, "load_settings", loader)
    monkeypatch.setattr(main, "open_checkpointer", database)
    with pytest.raises(ValueError, match="missing configuration"), TestClient(main.app):
        pass
    database.assert_not_called()
    failures = [record for record in caplog.records if record.exc_info]
    assert len(failures) == 1
    assert failures[0].getMessage() == "应用启动失败"


def test_database_error_aborts_startup(runtime, monkeypatch):
    """模拟数据库不可用，确认应用不暴露未初始化的 Agent。"""
    monkeypatch.setattr(main, "open_checkpointer", Mock(side_effect=RuntimeError("database unavailable")))
    with pytest.raises(RuntimeError, match="database unavailable"), TestClient(main.app):
        pass
    assert not hasattr(main.app.state, "chat_agent")


def test_build_error_closes_database(runtime, monkeypatch):
    """模拟图组装失败，确认此前已打开的数据库仍被关闭。"""
    _, events = runtime
    monkeypatch.setattr(main, "build_agent", Mock(side_effect=RuntimeError("build failed")))
    with pytest.raises(RuntimeError, match="build failed"), TestClient(main.app):
        pass
    assert events == ["open", "close"]


def test_imports_do_not_load_configuration_connect_or_invoke():
    """在独立进程禁止外部副作用，验证所有入口的导入保持惰性。"""
    script = """
from unittest.mock import patch
import importlib
import logging
import os

before = dict(os.environ)
handlers = list(logging.getLogger().handlers)
level = logging.getLogger().level
def forbidden(*args, **kwargs):
    '''禁止导入期间触发配置读取、连接或调用，以立即暴露外部副作用。'''
    raise AssertionError('external side effect during import')

with patch('dotenv.dotenv_values', forbidden), \\
     patch('dotenv.load_dotenv', forbidden), \\
     patch('langchain_openai.ChatOpenAI.__init__', forbidden), \\
     patch('langgraph.checkpoint.postgres.PostgresSaver.from_conn_string', forbidden), \\
     patch('logging.config.dictConfig', forbidden), \\
     patch('uvicorn.run', forbidden):
    for name in (
        'app.config.settings', 'app.config.logging', 'app.db.checkpoint', 'app.agents.models',
        'app.errors.codes', 'app.errors.exceptions', 'app.schemas.response', 'app.api.exception_handlers',
        'app.api.dependencies', 'app.api.routes.chat', 'app.api.router',
        'app.agents.factory', 'app.agents.agent', 'app.agents.__main__', 'app.main', 'app.__main__'
    ):
        importlib.import_module(name)
assert dict(os.environ) == before
assert logging.getLogger().handlers == handlers
assert logging.getLogger().level == level
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_cli_uses_shared_runtime(monkeypatch, capsys):
    """验证命令行先配置日志，再复用同一组装流程并输出纯文本回复。"""
    cli = importlib.import_module("app.agents.__main__")
    events = []
    graph = Mock()
    graph.invoke.return_value = {"messages": [AIMessage(content="CLI reply")]}
    def business_settings():
        """确认日志已初始化后返回业务配置替身，验证命令行启动顺序。"""
        cli.configure_logging.assert_called_once_with(LoggingSettings())
        return object()

    monkeypatch.setattr(cli, "load_settings", business_settings)
    monkeypatch.setattr(cli, "create_model", lambda settings: object())
    monkeypatch.setattr(cli, "build_agent", lambda model, tools, saver: graph)

    @contextmanager
    def connection(settings):
        """提供命令行可用的资源替身，并记录退出时关闭连接。"""
        events.append("open")
        try:
            yield object()
        finally:
            events.append("close")

    monkeypatch.setattr(cli, "open_checkpointer", connection)
    cli.main()
    assert capsys.readouterr().out.strip() == "CLI reply"
    assert graph.invoke.call_args.args[0]["messages"][0].content == cli.MESSAGE
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
    graph = Mock()
    graph.invoke.side_effect = failure
    monkeypatch.setattr(cli, "load_settings", lambda: object())
    monkeypatch.setattr(cli, "create_model", lambda settings: object())
    monkeypatch.setattr(cli, "build_agent", lambda model, tools, saver: graph)
    events = []

    @contextmanager
    def connection(settings):
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
