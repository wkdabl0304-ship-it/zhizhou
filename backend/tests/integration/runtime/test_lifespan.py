"""生命周期集成测试：验证正式 lifespan 的启动、复用、失败和释放。"""

import logging
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.core.settings import LoggingSettings
from tests.support.fakes.services import A, B
from tests.support.sse import parse_events


def test_chat_and_lifespan(runtime, caplog):
    """验证多次 HTTP 调用共用启动资源、返回 SSE 成功事件并在退出时清理。"""
    graph, events = runtime.graph, runtime.events
    with caplog.at_level(logging.INFO, logger="app.main"), TestClient(runtime.app) as client:
        assert events == ["open", "build"]
        for thread in [A, A, B]:
            response = client.post("/api/chat", json={"message": "你好", "conversation_id": thread})
            assert response.status_code == 200
            received = parse_events(response)
            assert [event.event for event in received] == ["start", "delta", "delta", "done"]
            assert received[-1].payload == {
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
    assert not hasattr(runtime.app.state, "chat_agent")
    assert [record.getMessage() for record in caplog.records if record.name == "app.main"] == [
        "应用启动完成", "应用资源已关闭",
    ]
    main.configure_logging.assert_called_once_with(LoggingSettings())


def test_configuration_error_aborts_startup(runtime, monkeypatch, caplog):
    """验证先初始化日志，再加载业务配置，配置失败时不连接数据库。"""
    def fail_configuration():
        """确认日志已准备好后模拟缺少业务配置，使测试覆盖启动失败路径。"""
        main.configure_logging.assert_called_once_with(LoggingSettings())
        raise ValueError("missing configuration")

    loader = Mock(side_effect=fail_configuration)
    database = Mock()
    monkeypatch.setattr(main, "load_settings", loader)
    monkeypatch.setattr(main, "open_checkpointer", database)
    with pytest.raises(ValueError, match="missing configuration"), TestClient(runtime.app):
        pass
    database.assert_not_called()
    failures = [record for record in caplog.records if record.exc_info]
    assert len(failures) == 1
    assert failures[0].getMessage() == "应用启动失败"


def test_database_error_aborts_startup(runtime, monkeypatch):
    """模拟数据库不可用，确认应用不暴露未初始化的 Agent。"""
    monkeypatch.setattr(main, "open_checkpointer", Mock(side_effect=RuntimeError("database unavailable")))
    with pytest.raises(RuntimeError, match="database unavailable"), TestClient(runtime.app):
        pass
    assert not hasattr(runtime.app.state, "chat_agent")


def test_build_error_closes_database(runtime, monkeypatch):
    """模拟图组装失败，确认此前已打开的数据库仍被关闭。"""
    events = runtime.events
    monkeypatch.setattr(main, "build_agent", Mock(side_effect=RuntimeError("build failed")))
    with pytest.raises(RuntimeError, match="build failed"), TestClient(runtime.app):
        pass
    assert events == ["open", "close"]
