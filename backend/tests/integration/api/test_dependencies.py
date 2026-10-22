"""依赖集成测试：验证 Agent 实例复用与依赖覆盖。"""

from fastapi import Request
from fastapi.testclient import TestClient

from app.agents.agent import ChatAgent
from app.api.dependencies import get_chat_agent
from tests.support.fakes.chat import GraphStub
from tests.support.fakes.services import OVERRIDE, A
from tests.support.sse import parse_events


def test_chat_dependency_reuses_initialized_agent(runtime, monkeypatch):
    """观察真实请求的依赖解析，确认多轮调用复用已初始化的 Agent 和连接。"""
    graph, events = runtime.graph, runtime.events
    observed = []

    def observe_agent(request: Request):
        """委托真实依赖并记录其结果，用于检查请求间是否复用同一资源。"""
        agent = get_chat_agent(request)
        observed.append(agent)
        return agent

    monkeypatch.setitem(runtime.app.dependency_overrides, get_chat_agent, observe_agent)
    with TestClient(runtime.app) as client:
        initialized_agent = runtime.app.state.chat_agent
        for message in ("第一轮", "第二轮"):
            response = client.post("/api/chat", json={"message": message, "conversation_id": A})
            assert response.status_code == 200
        assert observed == [initialized_agent, initialized_agent]
        assert events == ["open", "build"]
    assert len(graph.calls) == 2
    assert events == ["open", "build", "close"]


def test_chat_dependency_can_be_overridden(runtime, monkeypatch):
    """验证接口通过公共依赖取得 Agent，测试替身可替换它而不执行原图。"""
    graph = runtime.graph
    replacement_graph = GraphStub("依赖替身回复")
    replacement = ChatAgent(replacement_graph)

    def override_agent():
        """为请求返回独立的 Agent 替身，不读取或重建应用资源。"""
        return replacement

    monkeypatch.setitem(runtime.app.dependency_overrides, get_chat_agent, override_agent)
    with TestClient(runtime.app) as client:
        response = client.post("/api/chat", json={"message": "你好", "conversation_id": OVERRIDE})
    assert response.status_code == 200
    assert parse_events(response)[-1].payload == {
        "code": 0, "message": "成功",
        "data": {"reply": "依赖替身回复", "conversation_id": OVERRIDE, "message_id": "reply-1"},
    }
    assert replacement_graph.calls[0][0]["messages"][0].content == "你好"
    assert graph.calls == []
