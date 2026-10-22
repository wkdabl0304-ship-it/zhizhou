"""验证聊天 SSE 接口、异步生命周期、错误边界和命令行兼容入口。

将外部资源替换为测试对象，并隔离日志初始化，保留 pytest 的日志捕获。
"""

import importlib
import json
import logging
import os
import runpy
import subprocess
import sys
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from chat_fakes import GraphStub, StubChatModel
from fastapi import Request
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from service_fakes import OVERRIDE, A, B, MemoryConversationService

from app.agents.agent import ChatAgent
from app.agents.factory import build_agent
from app.agents.tools.weather import get_weather
from app.api.dependencies import get_chat_agent, get_current_user
from app.config.settings import LoggingSettings
from app.errors.codes import ErrorCode
from app.errors.exceptions import BusinessError

main = importlib.import_module("app.main")


def parse_events(response):
    """解析测试响应中的 SSE 事件，JSON 中的换行不会被误判为事件边界。"""
    result = []
    for block in response.text.strip().split("\n\n"):
        lines = block.splitlines()
        result.append({"event": lines[0].removeprefix("event: "), "payload": json.loads(lines[1].removeprefix("data: "))})
    return result


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
    graph = GraphStub()
    settings = object()
    model = object()
    @asynccontextmanager
    async def business_database(actual):
        """隔离业务引擎，不让生命周期测试连接真实数据库。"""
        yield object()
    def current_user():
        """传输测试绕过身份解析，真实认证在独立测试中验证。"""
        return Mock(id=UUID(A))
    monkeypatch.setattr(main, "open_business_database", business_database)
    monkeypatch.setattr(main, "AuthService", Mock(return_value=Mock(initialize=AsyncMock())))
    monkeypatch.setattr(main, "ConversationService", MemoryConversationService)
    monkeypatch.setitem(main.app.dependency_overrides, get_current_user, current_user)
    saver = object()
    monkeypatch.setattr(main, "load_settings", lambda: settings)
    monkeypatch.setattr(main, "create_model", lambda actual: model if actual is settings else None)

    @asynccontextmanager
    async def open_checkpointer(actual):
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
    """验证多次 HTTP 调用共用启动资源、返回 SSE 成功事件并在退出时清理。"""
    graph, events = runtime
    with caplog.at_level(logging.INFO, logger="app.main"), TestClient(main.app) as client:
        assert events == ["open", "build"]
        for thread in [A, A, B]:
            response = client.post("/api/chat", json={"message": "你好", "conversation_id": thread})
            assert response.status_code == 200
            received = parse_events(response)
            assert [event["event"] for event in received] == ["start", "delta", "delta", "done"]
            assert received[-1]["payload"] == {
                "code": 0, "message": "成功",
                "data": {"reply": "你好", "conversation_id": thread, "message_id": "reply-1"},
            }
            assert response.headers["content-type"].startswith("text/event-stream")
            assert response.headers["cache-control"] == "no-cache"
            assert response.headers["x-accel-buffering"] == "no"
            assert graph.calls[-1][1]["config"]["configurable"]["thread_id"] == f"conversation:{thread}"
        assert events == ["open", "build"]
        assert client.get("/docs").status_code == 200
    assert events == ["open", "build", "close"]
    assert not hasattr(main.app.state, "chat_agent")
    assert [record.getMessage() for record in caplog.records if record.name == "app.main"] == [
        "应用启动完成", "应用资源已关闭",
    ]
    main.configure_logging.assert_called_once_with(LoggingSettings())


@pytest.mark.parametrize("body", [
    {}, {"conversation_id": A},
    {"message": "", "conversation_id": A},
    {"message": " \n\t", "conversation_id": A},
    {"message": "hi", "conversation_id": ""},
    {"message": "hi", "conversation_id": " \t"},
    {"message": None, "conversation_id": A},
    {"message": "hi", "conversation_id": 123},
])
def test_invalid_request_does_not_invoke_agent(runtime, body):
    """验证各类非法字段返回统一 422，并在进入 Agent 之前被拒绝。"""
    graph, _ = runtime
    with TestClient(main.app) as client:
        response = client.post("/api/chat", json=body)
        assert response.status_code == 422
        assert response.json() == {"code": 42200, "message": "请求参数校验失败", "data": None}
    assert graph.calls == []


def test_model_error_returns_generic_error_and_logs_details(runtime, caplog):
    """验证模型失败返回安全的 SSE 错误事件，底层细节只进入一次服务端日志。"""
    graph, _ = runtime
    graph.failure = RuntimeError("private-provider-error")
    with TestClient(main.app) as client, caplog.at_level(logging.ERROR):
        response = client.post("/api/chat", json={"message": "hi", "conversation_id": A})
    assert response.status_code == 200
    assert [event["event"] for event in parse_events(response)] == ["start", "error"]
    assert parse_events(response)[-1]["payload"] == {"code": 50001, "message": "对话执行失败，请稍后重试", "data": None}
    assert "private-provider-error" not in response.text
    assert "private-provider-error" in caplog.text
    failures = [record for record in caplog.records if record.exc_info]
    assert len(failures) == 1
    assert failures[0].name == "app.agents.agent"
    assert failures[0].conversation_id == A


def test_business_error_from_agent_is_http_200_with_catalog_message(runtime, caplog):
    """验证 Agent 业务异常保留数字码和中央解释，使用 HTTP 200 且无堆栈。"""
    graph, _ = runtime
    error = BusinessError(ErrorCode.BUSINESS_ERROR)
    graph.failure = error
    with caplog.at_level(logging.WARNING), TestClient(main.app) as client:
        response = client.post("/api/chat", json={"message": "private-request", "conversation_id": A})
    assert response.status_code == 200
    assert parse_events(response)[-1]["payload"] == {"code": 20000, "message": "业务处理失败", "data": None}
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
    assert graph.calls == []


def test_openapi_documents_sse_and_uniform_pre_stream_errors(runtime):
    """OpenAPI 成功类型仅为 SSE，示例涵盖终止事件；参数及框架错误仍为 JSON。"""
    with TestClient(main.app) as client:
        schema = client.get("/openapi.json").json()
    assert "openapi" in schema and "code" not in schema
    assert "/chat" not in schema["paths"]
    assert "/api/api/chat" not in schema["paths"]
    operation = schema["paths"]["/api/chat"]["post"]
    assert operation["tags"] == ["聊天"]
    responses = operation["responses"]
    assert set(responses["200"]["content"]) == {"text/event-stream"}
    content = responses["200"]["content"]["text/event-stream"]
    assert "event: done" in content["examples"]["success"]["value"]
    for name in ("delta", "tool_call", "tool_start", "tool_end"):
        assert f"event: {name}" in content["examples"]["success"]["value"]
    assert "reasoning_delta" not in str(operation)
    assert "event: tool_error" in content["examples"]["tool_error"]["value"]
    assert "event: error" in content["examples"]["error"]["value"]
    for status in ("404", "405", "422", "500"):
        reference = responses[status]["content"]["application/json"]["schema"]["$ref"]
        error_schema = schema["components"]["schemas"][reference.split("/")[-1]]
        assert set(error_schema["properties"]) == {"code", "message", "data"}
    assert "HTTPValidationError" not in schema["components"]["schemas"]


def test_api_streams_real_tool_execution_as_process_events(runtime, monkeypatch):
    """真实图的工具请求、开始及结果经 SSE 路由正确编码，不误判为 done。"""
    agent = ChatAgent(build_agent(StubChatModel(), [get_weather], InMemorySaver()))

    def override_agent():
        """给请求注入真实图和内存保存器，生命周期仍由 runtime 隔离外部资源。"""
        return agent

    monkeypatch.setitem(main.app.dependency_overrides, get_chat_agent, override_agent)
    with TestClient(main.app) as client:
        response = client.post("/api/chat", json={"message": "天气", "conversation_id": A})
    events = parse_events(response)
    names = [event["event"] for event in events]
    assert names[:5] == ["start", "delta", "tool_call", "tool_start", "tool_end"]
    assert events[1]["payload"]["data"]["text"] == "我准备调用 get_weather 获取所需信息。"
    assert names[-1] == "done" and names.count("done") == 1
    call, started, ended = [events[index]["payload"]["data"] for index in (2, 3, 4)]
    assert call["tool_call_id"] == started["tool_call_id"] == ended["tool_call_id"] == "weather-1"
    assert call["arguments"] == started["arguments"] == {"city": "上海"}
    assert ended["output"] == "上海今天晴天，温度 25°C"
    for event in events:
        assert event["payload"]["code"] == 0
        assert event["payload"]["data"]["conversation_id"] == A
        assert "event" not in event["payload"]["data"]


@pytest.mark.parametrize("method,path,status,code", [
    ("POST", "/chat", 404, 40400),
    ("GET", "/api/chat", 405, 40500),
])
def test_chat_migration_rejects_old_path_and_wrong_method(runtime, method, path, status, code):
    """确认旧路径已移除，新路径只接受 POST，并继续使用统一协议错误响应。"""
    graph, _ = runtime
    with TestClient(main.app) as client:
        response = client.request(method, path, json={"message": "你好", "conversation_id": A})
    assert response.status_code == status
    assert response.json()["code"] == code
    assert response.json()["data"] is None
    if status == 405:
        assert "POST" in response.headers["allow"]
    assert graph.calls == []


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
            response = client.post("/api/chat", json={"message": message, "conversation_id": A})
            assert response.status_code == 200
        assert observed == [initialized_agent, initialized_agent]
        assert events == ["open", "build"]
    assert len(graph.calls) == 2
    assert events == ["open", "build", "close"]


def test_chat_dependency_can_be_overridden(runtime, monkeypatch):
    """验证接口通过公共依赖取得 Agent，测试替身可替换它而不执行原图。"""
    graph, _ = runtime
    replacement_graph = GraphStub("依赖替身回复")
    replacement = ChatAgent(replacement_graph)

    def override_agent():
        """为请求返回独立的 Agent 替身，不读取或重建应用资源。"""
        return replacement

    monkeypatch.setitem(main.app.dependency_overrides, get_chat_agent, override_agent)
    with TestClient(main.app) as client:
        response = client.post("/api/chat", json={"message": "你好", "conversation_id": OVERRIDE})
    assert response.status_code == 200
    assert parse_events(response)[-1]["payload"] == {
        "code": 0, "message": "成功",
        "data": {"reply": "依赖替身回复", "conversation_id": OVERRIDE, "message_id": "reply-1"},
    }
    assert replacement_graph.calls[0][0]["messages"][0].content == "你好"
    assert graph.calls == []


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
import json
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
     patch('app.agents.models.DeepSeekChatModel.__init__', forbidden), \\
     patch('langgraph.checkpoint.postgres.aio.AsyncPostgresSaver.from_conn_string', forbidden), \\
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
    graph = GraphStub("CLI reply")
    def business_settings():
        """确认日志已初始化后返回业务配置替身，验证命令行启动顺序。"""
        cli.configure_logging.assert_called_once_with(LoggingSettings())
        return object()

    monkeypatch.setattr(cli, "load_settings", business_settings)
    monkeypatch.setattr(cli, "create_model", lambda settings: object())
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
    monkeypatch.setattr(cli, "load_settings", lambda: object())
    monkeypatch.setattr(cli, "create_model", lambda settings: object())
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
