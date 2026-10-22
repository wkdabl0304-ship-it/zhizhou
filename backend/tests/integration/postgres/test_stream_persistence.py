"""PostgreSQL 集成测试：独立临时库验证取消保存和最终提交失败。"""

import asyncio
from contextlib import aclosing

import pytest
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk

from app.agents.agent import ChatAgent
from app.schemas.chat import ChatDelta
from tests.support.fakes.chat import StubChatModel
from tests.support.postgres import open_runtime as runtime, account
from tests.support.sse import parse_events as events

pytestmark = pytest.mark.postgres


@pytest.mark.anyio
async def test_cancellation_persists_partial_history_and_releases_lock(postgres_settings):
    """验证取消聊天会保存已公开的历史片段，并释放流与数据库执行锁。

    在模型等待期间主动取消，通过真实数据库核对中断状态及已收片段。
    """

    class PausedModel(StubChatModel):
        """先输出公开片段再等待取消，entered/cleaned 让生命周期可被准确观察。"""

        entered: object
        cleaned: object

        async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
            """保持模型未完成，finally 标记内部异步流已释放。"""
            try:
                yield ChatGenerationChunk(
                    message=AIMessageChunk(content="未完成的公开正文", id="partial")
                )
                self.entered.set()
                await asyncio.Event().wait()
            finally:
                self.cleaned.set()

    async with asyncio.timeout(15):
        entered, cleaned, visible = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async with runtime(postgres_settings, PausedModel(entered=entered, cleaned=cleaned)) as environment:
            auth = environment.auth
            service = environment.conversations
            graph = environment.graph
            user, _ = await account(auth)
            captured = []

            async def consume():
                """在正式请求上下文内消费，取消时让 prepare 的 finally 完成落库。"""
                async with service.prepare(user.id, "请求取消", None) as prepared:
                    captured.append(prepared)
                    async with aclosing(
                        service.stream(prepared, ChatAgent(graph))
                    ) as stream:
                        async for event in stream:
                            if isinstance(event, ChatDelta):
                                visible.set()

            task = asyncio.create_task(consume())
            await visible.wait()
            await entered.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert cleaned.is_set()
            content = await service.content(
                user.id, captured[0].conversation_id, 20, None
            )
            assert content.items[0].status == "interrupted"
            assert (
                content.items[0].public_events[0]["data"]["text"] == "未完成的公开正文"
            )
            assert content.items[0].assistant_content is None
            async with service.prepare(
                user.id, "锁应可再次取得", captured[0].conversation_id
            ):
                pass


@pytest.mark.anyio
async def test_final_commit_failure_never_sends_done(postgres_settings, monkeypatch):
    """验证最终业务提交失败时不能向客户端交付成功确认。

    即使 checkpoint 已保存，HTTP 也只能发送 error，业务历史不能标记完成。
    """

    async with runtime(postgres_settings) as environment:
        auth = environment.auth
        service = environment.conversations
        client = environment.client
        _user, headers = await account(auth)
        real_persist = service.persist

        async def failing_persist(prepared, **kwargs):
            """模拟业务最终事务失败，不影响错误快照和取消清理的数据库访问。"""
            if kwargs.get("status") == "completed":
                raise RuntimeError("private-final-storage-error")
            await real_persist(prepared, **kwargs)

        monkeypatch.setattr(service, "persist", failing_persist)
        response = await client.post(
            "/api/chat", headers=headers, json={"message": "你好"}
        )
        received = events(response)
        assert received[-1][0] == "error" and all(
            name != "done" for name, _ in received
        )
        assert "private-final-storage-error" not in response.text
        conversation_id = received[0][1]["data"]["conversation_id"]
        data = (
            await client.get(
                f"/api/conversations/{conversation_id}", headers=headers
            )
        ).json()["data"]
        assert data["items"][0]["status"] == "failed"
        assert data["items"][0]["assistant_content"] is None
