"""聊天接口集成测试：通过独立应用验证 SSE、校验和错误边界。"""

import logging

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from app.agents.agent import ChatAgent
from app.agents.factory import build_agent
from app.agents.tools.weather import get_weather
from app.api.dependencies import get_chat_agent
from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import BusinessError
from tests.support.fakes.chat import StubChatModel
from tests.support.fakes.services import A
from tests.support.sse import parse_events


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
    graph = runtime.graph
    with TestClient(runtime.app) as client:
        response = client.post("/api/chat", json=body)
        assert response.status_code == 422
        assert response.json() == {"code": 42200, "message": "请求参数校验失败", "data": None}
    assert graph.calls == []


def test_model_error_returns_generic_error_and_logs_details(runtime, caplog):
    """验证模型失败返回安全的 SSE 错误事件，底层细节只进入一次服务端日志。"""
    graph = runtime.graph
    graph.failure = RuntimeError("private-provider-error")
    with TestClient(runtime.app) as client, caplog.at_level(logging.ERROR):
        response = client.post("/api/chat", json={"message": "hi", "conversation_id": A})
    assert response.status_code == 200
    assert [event.event for event in parse_events(response)] == ["start", "error"]
    assert parse_events(response)[-1].payload == {"code": 50001, "message": "对话执行失败，请稍后重试", "data": None}
    assert "private-provider-error" not in response.text
    assert "private-provider-error" in caplog.text
    failures = [record for record in caplog.records if record.exc_info]
    assert len(failures) == 1
    assert failures[0].name == "app.agents.agent"
    assert failures[0].conversation_id == A


def test_business_error_from_agent_is_http_200_with_catalog_message(runtime, caplog):
    """验证 Agent 业务异常保留数字码和中央解释，使用 HTTP 200 且无堆栈。"""
    graph = runtime.graph
    error = BusinessError(ErrorCode.BUSINESS_ERROR)
    graph.failure = error
    with caplog.at_level(logging.WARNING), TestClient(runtime.app) as client:
        response = client.post("/api/chat", json={"message": "private-request", "conversation_id": A})
    assert response.status_code == 200
    assert parse_events(response)[-1].payload == {"code": 20000, "message": "业务处理失败", "data": None}
    records = [record for record in caplog.records if record.name.startswith("app.")]
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert not records[0].exc_info
    assert error.logged


def test_invalid_json_is_uniform_422_and_not_sent_to_agent(runtime):
    """验证无法解析的 JSON 返回统一 422，且不泄露输入或调用模型。"""
    graph = runtime.graph
    with TestClient(runtime.app) as client:
        response = client.post("/api/chat", content='{"private-input":', headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json() == {"code": 42200, "message": "请求参数校验失败", "data": None}
    assert "private-input" not in response.text
    assert graph.calls == []


def test_api_streams_real_tool_execution_as_process_events(runtime, monkeypatch):
    """真实图的工具请求、开始及结果经 SSE 路由正确编码，不误判为 done。"""
    agent = ChatAgent(build_agent(StubChatModel(), [get_weather], InMemorySaver()))

    def override_agent():
        """给请求注入真实图和内存保存器，生命周期仍由 runtime 隔离外部资源。"""
        return agent

    monkeypatch.setitem(runtime.app.dependency_overrides, get_chat_agent, override_agent)
    with TestClient(runtime.app) as client:
        response = client.post("/api/chat", json={"message": "天气", "conversation_id": A})
    events = parse_events(response)
    names = [event.event for event in events]
    assert names[:5] == ["start", "delta", "tool_call", "tool_start", "tool_end"]
    assert events[1].payload["data"]["text"] == "我准备调用 get_weather 获取所需信息。"
    assert names[-1] == "done" and names.count("done") == 1
    call, started, ended = [events[index].payload["data"] for index in (2, 3, 4)]
    assert call["tool_call_id"] == started["tool_call_id"] == ended["tool_call_id"] == "weather-1"
    assert call["arguments"] == started["arguments"] == {"city": "上海"}
    assert ended["output"] == "上海今天晴天，温度 25°C"
    for event in events:
        assert event.payload["code"] == 0
        assert event.payload["data"]["conversation_id"] == A
        assert "event" not in event.payload["data"]


@pytest.mark.parametrize("method,path,status,code", [
    ("POST", "/chat", 404, 40400),
    ("GET", "/api/chat", 405, 40500),
])
def test_chat_migration_rejects_old_path_and_wrong_method(runtime, method, path, status, code):
    """确认旧路径已移除，新路径只接受 POST，并继续使用统一协议错误响应。"""
    graph = runtime.graph
    with TestClient(runtime.app) as client:
        response = client.request(method, path, json={"message": "你好", "conversation_id": A})
    assert response.status_code == status
    assert response.json()["code"] == code
    assert response.json()["data"] is None
    if status == 405:
        assert "POST" in response.headers["allow"]
    assert graph.calls == []
