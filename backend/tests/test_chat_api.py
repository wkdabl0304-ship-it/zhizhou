import importlib
import logging
import os
import runpy
import subprocess
import sys
from contextlib import contextmanager
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

main = importlib.import_module("app.main")


@pytest.fixture
def runtime(monkeypatch):
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
        assert actual is settings
        events.append("open")
        try:
            yield saver
        finally:
            events.append("close")

    def build_agent(actual_model, tools, actual_saver):
        assert actual_model is model
        assert actual_saver is saver
        assert [tool.name for tool in tools] == ["get_weather"]
        events.append("build")
        return graph

    monkeypatch.setattr(main, "open_checkpointer", open_checkpointer)
    monkeypatch.setattr(main, "build_agent", build_agent)
    return graph, events


def test_chat_and_lifespan(runtime):
    graph, events = runtime
    with TestClient(main.app) as client:
        assert events == ["open", "build"]
        for thread in ["conversation-001", "conversation-001", "other"]:
            response = client.post("/chat", json={"message": "你好", "thread_id": thread})
            assert response.status_code == 200
            assert response.json() == {"reply": "你好", "thread_id": thread}
            assert graph.invoke.call_args.kwargs["config"]["configurable"]["thread_id"] == thread
        assert events == ["open", "build"]
        assert client.get("/docs").status_code == 200
    assert events == ["open", "build", "close"]
    assert not hasattr(main.app.state, "chat_agent")


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
    graph, _ = runtime
    with TestClient(main.app) as client:
        assert client.post("/chat", json=body).status_code == 422
    graph.invoke.assert_not_called()


def test_model_error_returns_generic_error_and_logs_details(runtime, caplog):
    graph, _ = runtime
    graph.invoke.side_effect = RuntimeError("private-provider-error")
    with TestClient(main.app) as client, caplog.at_level(logging.ERROR):
        response = client.post("/chat", json={"message": "hi", "thread_id": "a"})
    assert response.status_code == 500
    assert response.json() == {"detail": "对话执行失败，请稍后重试"}
    assert "private-provider-error" not in response.text
    assert "private-provider-error" in caplog.text


def test_configuration_error_aborts_startup(monkeypatch):
    loader = Mock(side_effect=ValueError("missing configuration"))
    database = Mock()
    monkeypatch.setattr(main, "load_settings", loader)
    monkeypatch.setattr(main, "open_checkpointer", database)
    with pytest.raises(ValueError, match="missing configuration"), TestClient(main.app):
        pass
    database.assert_not_called()


def test_database_error_aborts_startup(runtime, monkeypatch):
    monkeypatch.setattr(main, "open_checkpointer", Mock(side_effect=RuntimeError("database unavailable")))
    with pytest.raises(RuntimeError, match="database unavailable"), TestClient(main.app):
        pass
    assert not hasattr(main.app.state, "chat_agent")


def test_build_error_closes_database(runtime, monkeypatch):
    _, events = runtime
    monkeypatch.setattr(main, "build_agent", Mock(side_effect=RuntimeError("build failed")))
    with pytest.raises(RuntimeError, match="build failed"), TestClient(main.app):
        pass
    assert events == ["open", "close"]


def test_imports_do_not_load_configuration_connect_or_invoke():
    script = """
from unittest.mock import patch
import importlib
import os

before = dict(os.environ)
def forbidden(*args, **kwargs):
    raise AssertionError('external side effect during import')

with patch('dotenv.dotenv_values', forbidden), \\
     patch('dotenv.load_dotenv', forbidden), \\
     patch('langchain_openai.ChatOpenAI.__init__', forbidden), \\
     patch('langgraph.checkpoint.postgres.PostgresSaver.from_conn_string', forbidden):
    for name in (
        'app.config.settings', 'app.db.checkpoint', 'app.agents.models',
        'app.agents.factory', 'app.agents.agent', 'app.agents.__main__', 'app.main'
    ):
        importlib.import_module(name)
assert dict(os.environ) == before
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_cli_uses_shared_runtime(monkeypatch, capsys):
    cli = importlib.import_module("app.agents.__main__")
    events = []
    graph = Mock()
    graph.invoke.return_value = {"messages": [AIMessage(content="CLI reply")]}
    monkeypatch.setattr(cli, "load_settings", lambda: object())
    monkeypatch.setattr(cli, "create_model", lambda settings: object())
    monkeypatch.setattr(cli, "build_agent", lambda model, tools, saver: graph)

    @contextmanager
    def connection(settings):
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
    cli = importlib.import_module("app.agents.__main__")
    entry = Mock()
    monkeypatch.setattr(cli, "main", entry)
    with pytest.warns(RuntimeWarning, match="found in sys.modules"):
        runpy.run_module("app.agents.agent", run_name="__main__")
    entry.assert_called_once_with()
