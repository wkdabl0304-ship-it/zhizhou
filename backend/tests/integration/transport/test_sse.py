"""SSE 传输集成测试：真实回环 TCP 验证逐段交付、失败和断开取消。"""

import asyncio
import socket
from unittest.mock import Mock
from uuid import UUID

import httpx
import pytest
import uvicorn
from langchain_core.messages import AIMessage, AIMessageChunk

from app.agents.agent import ChatAgent
from app.api.dependencies import get_current_user
from tests.support.apps import make_app
from tests.support.fakes.services import A, MemoryConversationService
from tests.support.sse import read_event

pytestmark = pytest.mark.transport


@pytest.mark.anyio
async def test_real_uvicorn_delivers_incrementally_and_cancels_disconnected_request():
    """真实 TCP 验证首段先到、完整终止、流中异常和断开后取消，最终关闭服务器。"""

    async with asyncio.timeout(15):
        release, finished, cleaned = asyncio.Event(), asyncio.Event(), asyncio.Event()

        async def stream(inputs, **kwargs):
            """按输入模拟成功、半途失败或长期生成；取消时执行异步资源清理。"""
            text = inputs["messages"][0].content
            try:
                if text == "success":
                    yield "messages", (AIMessageChunk(content="", id="reply", additional_kwargs={"reasoning_content": "公开思考"}), {"langgraph_node": "model"})
                yield "messages", (AIMessageChunk(content="你好\n", id="reply"), {"langgraph_node": "model"})
                if text == "failure":
                    raise RuntimeError("private-provider-error")
                if text == "cancel":
                    await asyncio.Event().wait()
                await release.wait()
                yield "messages", (AIMessageChunk(content="世界", id="reply"), {"langgraph_node": "model"})
                yield "updates", {"model": {"messages": [AIMessage(content="你好\n世界", id="reply")]}}
                finished.set()
            finally:
                if text == "cancel":
                    await asyncio.sleep(0.01)
                    cleaned.set()

        app = make_app(agent=ChatAgent(Mock(astream=stream)), conversations=MemoryConversationService())
        def current_user():
            """TCP 传输回归注入已认证用户，避免与 JWT 集成测试重复耦合。"""
            return Mock(id=UUID(A))
        app.dependency_overrides[get_current_user] = current_user
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        config = uvicorn.Config(app, lifespan="off", log_config=None, access_log=False)
        server = uvicorn.Server(config)
        serving = asyncio.create_task(server.serve(sockets=[listener]))

        try:
            while not server.started:
                if serving.done():
                    serving.result()
                    raise AssertionError("server failed to start")
                await asyncio.sleep(0.001)
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=5) as client:
                async with client.stream("POST", "/api/chat", json={"message": "success", "conversation_id": A}) as response:
                    lines = response.aiter_lines()
                    assert response.status_code == 200
                    assert response.headers["content-type"].startswith("text/event-stream")
                    assert response.headers["cache-control"] == "no-cache"
                    assert response.headers["x-accel-buffering"] == "no"
                    assert (await read_event(lines))[0] == "start"
                    event, payload = await read_event(lines)
                    assert event == "delta" and payload["data"]["text"] == "你好\n"
                    assert not finished.is_set()
                    release.set()
                    assert (await read_event(lines))[0] == "delta"
                    event, payload = await read_event(lines)
                    assert event == "done" and payload["data"]["reply"] == "你好\n世界"
                    assert finished.is_set()
                    assert [line async for line in lines] == []
                async with client.stream("POST", "/api/chat", json={"message": "failure", "conversation_id": A}) as response:
                    body = (await response.aread()).decode()
                    assert "event: delta" in body and "event: error" in body
                    assert "event: done" not in body and "private-provider-error" not in body
                    assert '"code":50001' in body
                async with client.stream("POST", "/api/chat", json={"message": "cancel", "conversation_id": A}) as response:
                    lines = response.aiter_lines()
                    assert (await read_event(lines))[0] == "start"
                    assert (await read_event(lines))[0] == "delta"
                await cleaned.wait()
                assert app.state.chat_agent._locks == {}
        finally:
            server.should_exit = True
            try:
                await asyncio.wait_for(serving, 5)
            finally:
                listener.close()
