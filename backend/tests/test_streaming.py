"""验证 SSE 的实际传输、ASGI 断开取消、发送失败以及 Windows 循环配置。

本地 Uvicorn 仅监听临时回环端口，使用图替身，不连接数据库或外部模型。
所有服务器任务、客户端和套接字均在测试 finally 中关闭。
"""

import asyncio
import json
import socket
import sys
from unittest.mock import Mock
from uuid import UUID, uuid4

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from langchain_core.messages import AIMessage, AIMessageChunk
from service_fakes import A, MemoryConversationService

from app.agents.agent import ChatAgent
from app.api.dependencies import get_current_user
from app.api.exception_handlers import register_exception_handlers
from app.api.router import api_router
from app.api.routes.chat import chat
from app.core.event_loop import create_event_loop
from app.services.conversations import PreparedChat


@pytest.mark.parametrize("version", ["2.0", "2.4"])
@pytest.mark.parametrize("interruption", ["waiting", "generating", "send", "server"])
def test_disconnect_cleans_generator_and_conversation_lock(version, interruption, caplog):
    """各 ASGI 版本均在排队、模型等待、发送失败或服务器取消时等待清理完成。"""
    async def scenario():
        """显式控制生成及断开时机，确认响应返回前慢速异步清理已经结束。"""
        entered, cleaned, delta_sent = asyncio.Event(), asyncio.Event(), asyncio.Event()

        async def stream(inputs, **kwargs):
            """先输出一段再等待取消，finally 执行可观察的异步清理。"""
            try:
                yield "messages", (AIMessageChunk(content="半段", id="partial"), {"langgraph_node": "model"})
                entered.set()
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0.01)
                cleaned.set()

        agent = ChatAgent(Mock(astream=stream))
        holder = None
        if interruption == "waiting":
            holder = asyncio.create_task(agent.achat("first", A))
            await entered.wait()
        response = await chat(PreparedChat(UUID(A), uuid4(), "next", False), agent, MemoryConversationService())

        async def send(message):
            """观察真实编码后的增量，按场景模拟底层 socket 发送失败。"""
            if b"event: delta" in message.get("body", b""):
                delta_sent.set()
                if interruption == "send":
                    raise OSError("client disconnected")

        async def receive():
            """在模型等待或第二轮排队后发送 disconnect，其他场景等待被取消。"""
            if interruption == "waiting":
                while agent._locks[A].users != 2:
                    await asyncio.sleep(0)
            elif interruption == "generating":
                await entered.wait()
            else:
                await asyncio.Event().wait()
            return {"type": "http.disconnect"}

        task = asyncio.create_task(response({"type": "http", "asgi": {"spec_version": version}}, receive, send))
        try:
            if interruption == "server":
                await entered.wait()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                await task
            if holder:
                assert agent._locks[A].users == 1
                assert not cleaned.is_set()
                holder.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await holder
            else:
                assert delta_sent.is_set()
            assert cleaned.is_set() and agent._locks == {}
        finally:
            # 测试断言失败也不遗留阻塞图或响应任务。
            for pending in (task, holder):
                if pending is not None and not pending.done():
                    pending.cancel()
            await asyncio.gather(*(pending for pending in (task, holder) if pending is not None), return_exceptions=True)

    asyncio.run(asyncio.wait_for(scenario(), 5))
    assert not [record for record in caplog.records if record.exc_info]


def test_real_uvicorn_delivers_incrementally_and_cancels_disconnected_request():
    """真实 TCP 验证首段先到、完整终止、流中异常和断开后取消，最终关闭服务器。"""
    async def scenario():
        """同一循环运行服务器及客户端，用事件阻止模型提前完成，避免依赖速度断言。"""
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

        app = FastAPI()
        app.state.chat_agent = ChatAgent(Mock(astream=stream))
        app.state.conversation_service = MemoryConversationService()
        def current_user():
            """TCP 传输回归注入已认证用户，避免与 JWT 集成测试重复耦合。"""
            return Mock(id=UUID(A))
        app.dependency_overrides[get_current_user] = current_user
        register_exception_handlers(app)
        app.include_router(api_router)
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        config = uvicorn.Config(app, lifespan="off", log_config=None, access_log=False)
        server = uvicorn.Server(config)
        serving = asyncio.create_task(server.serve(sockets=[listener]))

        async def read_event(lines):
            """读取一个完整 SSE 事件，逐行解析真实网络输入。"""
            event, data = "", None
            async for line in lines:
                if line.startswith("event: "):
                    event = line[7:]
                elif line.startswith("data: "):
                    data = json.loads(line[6:])
                elif not line:
                    return event, data
            raise AssertionError("SSE unexpectedly ended")

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

    with asyncio.Runner(loop_factory=create_event_loop) as runner:
        runner.run(asyncio.wait_for(scenario(), 15))


@pytest.mark.parametrize("reload", [False, True])
def test_uvicorn_loop_factory_for_normal_and_reload_startup(reload):
    """验证 Uvicorn 普通与 reload 配置都能导入工厂，在 Windows 创建 Selector 循环。"""
    config = uvicorn.Config("app.main:app", reload=reload, loop="app.core.event_loop:create_event_loop", log_config=None)
    factory = config.get_loop_factory()
    loop = factory()
    try:
        if sys.platform == "win32":
            assert isinstance(loop, asyncio.SelectorEventLoop)
        assert not loop.is_running()
    finally:
        loop.close()
