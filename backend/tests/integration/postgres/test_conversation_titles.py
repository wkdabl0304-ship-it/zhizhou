"""标题业务集成：真实数据库与聊天图验证生成时序、用户隔离、重试及并发改名。"""

import asyncio
import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.agents.agent import checkpoint_key
from app.models import ChatTurn, Conversation
from app.schemas.chat import ChatResponse
from app.services import conversations as conversation_module
from tests.support.fakes.chat import StubChatModel
from tests.support.postgres import account, open_runtime, send
from tests.support.sse import parse_events

pytestmark = [pytest.mark.postgres, pytest.mark.anyio]


async def title_row(runtime, conversation_id):
    """用独立连接读取标题及时间，确保断言观察的是已提交结果。"""
    async with runtime.database.sessions() as session:
        return await session.get(Conversation, UUID(str(conversation_id)))


async def consume(runtime, prepared, events):
    """消费正式服务流并记录事件，让测试能够在标题生成屏障处检查提交顺序。"""
    async for event in runtime.conversations.stream(prepared, runtime.agent):
        events.append(event)


async def test_title_commits_before_done_without_polluting_history_or_model_selection(postgres_settings):
    """回答先落库，标题生成期间仍未 done；标题使用本轮快照且不进入正文或 checkpoint。"""
    async with open_runtime(postgres_settings) as runtime:
        user, headers = await account(runtime.auth)
        model = runtime.title_model
        model.reply = "  正式\n标题  "
        model.release = asyncio.Event()
        question = "  第一条\n问题\t" + "很长的正文" * 8
        async with asyncio.timeout(10), runtime.conversations.prepare(user.id, question, None) as prepared:
            events = []
            task = asyncio.create_task(consume(runtime, prepared, events))
            try:
                await model.started.wait()
                row = await title_row(runtime, prepared.conversation_id)
                assert row.title == " ".join(question.split())[:24]
                assert row.title_source == "provisional"
                before_time = row.last_message_at
                assert prepared.terminal and not any(isinstance(event, ChatResponse) for event in events)
                async with runtime.database.sessions() as session:
                    turn = await session.get(ChatTurn, prepared.turn_id)
                    assert turn.status == "completed" and turn.assistant_content == question
                model.release.set()
                await task
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        row = await title_row(runtime, prepared.conversation_id)
        assert row.title == "正式 标题" and row.title_source == "auto"
        assert row.last_message_at == before_time and row.updated_at >= before_time
        assert isinstance(events[-1], ChatResponse)
        assert model.snapshots == [prepared.model_runtime] and len(runtime.snapshots) == 1
        detail = (await runtime.client.get(f"/api/conversations/{row.id}", headers=headers)).json()["data"]
        assert detail["conversation"]["title"] == "正式 标题"
        assert "title_source" not in detail["conversation"]
        assert "正式 标题" not in json.dumps(detail["items"], ensure_ascii=False)
        snapshot = await runtime.graph.aget_state({"configurable": {"thread_id": checkpoint_key(str(row.id))}})
        assert [message.type for message in snapshot.values["messages"]] == ["human", "ai"]
        assert snapshot.values["messages"][0].content == question
        await send(runtime.client, headers, "继续", str(row.id))
        assert len(model.snapshots) == 1
        response = await runtime.client.patch(f"/api/conversations/{row.id}/title", headers=headers,
                                             json={"title": "自动完成后手动改名"})
        assert response.json()["data"]["title"] == "自动完成后手动改名"
        assert (await title_row(runtime, row.id)).title_source == "manual"


@pytest.mark.parametrize("phase", ["before", "during"])
async def test_manual_title_wins_even_when_equal_to_provisional(postgres_settings, phase):
    """持有聊天执行锁时仍能改名；相同临时标题也受保护，过期自动结果不得覆盖。"""
    async with open_runtime(postgres_settings) as runtime:
        user, headers = await account(runtime.auth)
        runtime.title_model.reply = "应被丢弃的自动标题"
        runtime.title_model.release = asyncio.Event()
        async with asyncio.timeout(10), runtime.conversations.prepare(user.id, "临时标题", None) as prepared:
            cid = prepared.conversation_id
            before = await title_row(runtime, cid)
            events = []
            task = None
            try:
                if phase == "during":
                    task = asyncio.create_task(consume(runtime, prepared, events))
                    await runtime.title_model.started.wait()
                response = await runtime.client.patch(f"/api/conversations/{cid}/title", headers=headers,
                                                     json={"title": "临时标题"})
                assert response.status_code == 200 and response.json()["code"] == 0
                assert (await title_row(runtime, cid)).title_source == "manual"
                if phase == "before":
                    task = asyncio.create_task(consume(runtime, prepared, events))
                runtime.title_model.release.set()
                await task
            finally:
                if task is not None:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
        after = await title_row(runtime, cid)
        assert after.title == "临时标题" and after.title_source == "manual"
        assert after.last_message_at == before.last_message_at
        assert len(runtime.title_model.snapshots) == (1 if phase == "during" else 0)
        await send(runtime.client, headers, "下一轮", str(cid))
        assert (await title_row(runtime, cid)).title == "临时标题"
        assert len(runtime.title_model.snapshots) == (1 if phase == "during" else 0)


@pytest.mark.parametrize("failure", ["provider", "blank", "long", "timeout", "read", "save"])
async def test_title_failure_keeps_chat_successful_and_retries_original_question(postgres_settings, monkeypatch, caplog, failure):
    """标题各阶段失败均保留已完成聊天；下轮用首条问题和当前回答重试，日志不暴露细节。"""
    async with open_runtime(postgres_settings) as runtime:
        _, headers = await account(runtime.auth)
        model = runtime.title_model
        with monkeypatch.context() as changes:
            if failure == "provider":
                model.failure = RuntimeError("私有凭据与正文不可进入日志")
            elif failure in {"blank", "long"}:
                model.reply = "\n\t" if failure == "blank" else "长" * 101
            elif failure == "timeout":
                model.release = asyncio.Event()
                changes.setattr(conversation_module, "TITLE_TIMEOUT_SECONDS", 0.1)
            else:
                async def fail_database(*args, **kwargs):
                    """模拟标题短事务故障，不影响已经成功提交的业务回答。"""
                    raise RuntimeError("私有凭据与正文不可进入日志")
                changes.setattr(conversation_module.repository, "title_question" if failure == "read" else "update_title", fail_database)
            cid, events = await send(runtime.client, headers, "最初的问题")
        row = await title_row(runtime, cid)
        assert row.title == "最初的问题" and row.title_source == "provisional"
        assert events[-1].event == "done"
        content = (await runtime.client.get(f"/api/conversations/{cid}", headers=headers)).json()["data"]
        assert content["items"][0]["status"] == "completed"
        assert "私有凭据" not in caplog.text
        if failure != "read":
            assert model.closed and model.stream_closed
        model.failure, model.reply, model.release = None, "成功重试的标题", None
        await send(runtime.client, headers, "后续问题", cid)
        row = await title_row(runtime, cid)
        assert row.title == "成功重试的标题" and row.title_source == "auto"
        payload = json.loads(model.messages[-1][-1].content)
        assert payload == {"question": "最初的问题", "answer": "最初的问题|后续问题"}


async def test_cancel_during_title_preserves_completed_chat_and_releases_lock(postgres_settings):
    """标题阶段取消会关闭模型，保留 completed 状态，释放执行锁并允许下轮重试。"""
    async with open_runtime(postgres_settings) as runtime:
        user, headers = await account(runtime.auth)
        runtime.title_model.release = asyncio.Event()
        captured = []

        async def run():
            """让被取消任务拥有 prepare 上下文，覆盖真实请求的锁及终态清理。"""
            async with runtime.conversations.prepare(user.id, "取消标题阶段", None) as prepared:
                captured.append(prepared)
                await consume(runtime, prepared, [])

        async with asyncio.timeout(10):
            task = asyncio.create_task(run())
            try:
                await runtime.title_model.started.wait()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        assert runtime.title_model.closed and runtime.title_model.stream_closed
        prepared = captured[0]
        content = await runtime.conversations.content(user.id, prepared.conversation_id, 20, None)
        assert content.items[0].status == "completed"
        assert (await title_row(runtime, prepared.conversation_id)).title_source == "provisional"
        runtime.title_model.release = None
        await send(runtime.client, headers, "继续", str(prepared.conversation_id))
        assert (await title_row(runtime, prepared.conversation_id)).title_source == "auto"


@pytest.mark.parametrize("status", ["failed", "interrupted"])
async def test_failed_chat_does_not_generate_title_and_next_success_retries(postgres_settings, status):
    """回答失败或尚未完成即中断时不调用标题模型，下轮成功后仍采用最初的问题。"""
    class FailingFirstModel(StubChatModel):
        """仅首条指定问题触发失败，其余请求保留真实图和历史续聊。"""

        def _generate(self, messages, **kwargs):
            """模拟首轮供应商故障，后续调用继续使用已有多轮替身。"""
            if messages[-1].content == "失败的首问":
                raise RuntimeError("首轮模型故障")
            return super()._generate(messages, **kwargs)

    async with open_runtime(postgres_settings, model=FailingFirstModel()) as runtime:
        user, headers = await account(runtime.auth)
        question = "失败的首问" if status == "failed" else "中断的首问"
        if status == "failed":
            response = await runtime.client.post("/api/chat", headers=headers, json={"message": question})
            events = parse_events(response)
            assert events[-1].event == "error"
            cid = events[0].payload["data"]["conversation_id"]
        else:
            async with runtime.conversations.prepare(user.id, question, None) as prepared:
                cid = str(prepared.conversation_id)
        assert not runtime.title_model.snapshots
        assert (await title_row(runtime, cid)).title_source == "provisional"
        detail = (await runtime.client.get(f"/api/conversations/{cid}", headers=headers)).json()["data"]
        assert detail["items"][0]["status"] == status
        await send(runtime.client, headers, "成功的第二问", cid)
        assert json.loads(runtime.title_model.messages[0][-1].content)["question"] == question
        assert (await title_row(runtime, cid)).title_source == "auto"


@pytest.mark.parametrize("owner_role,other_role", [("user", "super_admin"), ("super_admin", "user")])
async def test_rename_api_validation_ownership_visibility_and_order(postgres_settings, owner_role, other_role):
    """改名遵循认证和双向角色隔离，校验不产生副作用，不改变排序或模型选择。"""
    async with open_runtime(postgres_settings) as runtime:
        _, headers = await account(runtime.auth, owner_role)
        _, foreign = await account(runtime.auth, other_role)
        cid, _ = await send(runtime.client, headers, "较早的会话")
        await send(runtime.client, headers, "较新的会话")
        path = f"/api/conversations/{cid}/title"
        before = await title_row(runtime, cid)
        old_list = (await runtime.client.get("/api/conversations", headers=headers)).json()["data"]["items"]
        for body in ({}, {"title": None}, {"title": 123}, {"title": True}, {"title": []},
                     {"title": ""}, {"title": " \n\u3000"}, {"title": "中" * 101},
                     {"title": "标题", "title_source": "auto"}):
            response = await runtime.client.patch(path, headers=headers, json=body)
            assert response.status_code == 422 and response.json()["code"] == 42200
        assert (await runtime.client.patch(path, json={"title": "标题"})).status_code == 401
        for forbidden_path, forbidden_headers in [(path, foreign), (f"/api/conversations/{uuid4()}/title", headers)]:
            response = await runtime.client.patch(forbidden_path, headers=forbidden_headers, json={"title": "标题"})
            assert response.status_code == 404 and response.json()["code"] == 40401
        assert (await runtime.client.patch("/api/conversations/bad-id/title", headers=headers, json={"title": "标题"})).status_code == 422
        assert (await title_row(runtime, cid)).title == before.title
        response = await runtime.client.patch(path, headers=headers, json={"title": "  中文\n标题\t🙂  "})
        data = response.json()["data"]
        assert response.status_code == 200 and data["title"] == "中文 标题 🙂"
        assert data["conversation_id"] == cid and "title_source" not in data
        after = await title_row(runtime, cid)
        assert after.title_source == "manual" and after.last_message_at == before.last_message_at
        assert after.model_selection == before.model_selection and after.model_selection_version == before.model_selection_version
        new_list = (await runtime.client.get("/api/conversations", headers=headers)).json()["data"]["items"]
        assert [row["conversation_id"] for row in new_list] == [row["conversation_id"] for row in old_list]
        assert new_list[1]["title"] == data["title"]
        assert (await runtime.client.get(f"/api/conversations/{cid}", headers=headers)).json()["data"]["conversation"]["title"] == data["title"]
        # 选择失效不妨碍改名，返回值仍需像目录一样包含动态失效原因。
        model = (await runtime.model_config.list_models())[0]
        disabled = await runtime.client.patch(f"/api/model-config/models/{model.id}", headers=headers,
                                              json={"version": model.version, "enabled": False})
        assert disabled.json()["code"] == 0
        boundary = await runtime.client.patch(path, headers=headers, json={"title": "🙂" * 100})
        assert boundary.json()["data"]["title"] == "🙂" * 100
        assert boundary.json()["data"]["model_selection_issue"] == "model_disabled"
        assert len(runtime.snapshots) == 2 and len(runtime.title_model.snapshots) == 2
        await runtime.client.delete(f"/api/conversations/{cid}", headers=headers)
        response = await runtime.client.patch(path, headers=headers, json={"title": "删除后不能修改"})
        assert response.status_code == 404 and response.json()["code"] == 40401
