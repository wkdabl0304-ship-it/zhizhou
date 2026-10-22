"""独立 PostgreSQL 集成验收：真实迁移、ORM、认证、会话隔离、公开历史与并发锁。

通过 ZHIZHOU_TEST_POSTGRES=1 显式启用；fixture 创建随机数据库并在结束时销毁，
模型为本地替身，不调用真实供应商，也不修改开发库中的用户或 checkpoint。
"""

import asyncio
import json
import os
import subprocess
import sys
from contextlib import aclosing, asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import jwt
import pytest
from chat_fakes import StubChatModel
from conftest import run_async
from fastapi import FastAPI
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from sqlalchemy import inspect, update
from sqlalchemy.exc import IntegrityError

from app.agents.agent import ChatAgent, checkpoint_key
from app.agents.factory import build_agent
from app.agents.tools.weather import get_weather
from app.api.exception_handlers import register_exception_handlers
from app.api.router import api_router
from app.db.business import check_schema, open_business_database
from app.db.checkpoint import open_checkpointer
from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import RequestError
from app.models import ChatTurn, Conversation, User
from app.schemas.auth import LoginRequest, RegisterRequest
from app.schemas.chat import ChatDelta
from app.services.auth import AuthService
from app.services.conversations import ConversationService


@asynccontextmanager
async def runtime(settings, model=None):
    """为集成测试提供连接隔离数据库的完整后端运行环境。

    复用正式业务服务、路由和 PostgreSQL checkpoint，模型使用本地替身；
    yield 数据库、认证、会话服务、图与 HTTP 客户端，退出时关闭异步资源。
    """
    async with (
        open_business_database(settings) as database,
        open_checkpointer(settings) as checkpointer,
    ):
        auth = AuthService(database, settings)
        await auth.initialize()
        service = ConversationService(database)
        graph = build_agent(model or StubChatModel(), [get_weather], checkpointer)
        app = FastAPI()
        app.state.auth_service = auth
        app.state.conversation_service = service
        app.state.chat_agent = ChatAgent(graph)
        register_exception_handlers(app)
        app.include_router(api_router)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield database, auth, service, graph, client


async def account(auth, role="user"):
    """创建测试独享账号并取得 Bearer 请求头，名称随机化避免测试间相互依赖。"""
    username = "u_" + uuid4().hex[:20]
    registered = await auth.register(
        RegisterRequest(username=username, password="password-with-spaces ", role=role)
    )
    logged = await auth.login(
        LoginRequest(username=username.upper(), password="password-with-spaces ")
    )
    return registered, {"Authorization": f"Bearer {logged.access_token}"}


def events(response):
    """解析完整测试响应，不把 JSON 正文中的换行误当作 SSE 分隔符。"""
    result = []
    for block in response.text.strip().split("\n\n"):
        name, raw = block.splitlines()
        result.append(
            (name.removeprefix("event: "), json.loads(raw.removeprefix("data: ")))
        )
    return result


async def send(client, headers, message="天气", conversation_id=None):
    """发送一轮正式 HTTP 聊天，并返回服务端签发的业务 ID 与解析事件。"""
    body = {"message": message}
    if conversation_id is not None:
        body["conversation_id"] = str(conversation_id)
    response = await client.post("/api/chat", json=body, headers=headers)
    assert response.status_code == 200, response.text
    received = events(response)
    assert received[0][0] == "start" and received[-1][0] == "done", response.text
    assert "thread_id" not in response.text
    return received[0][1]["data"]["conversation_id"], received


def test_real_migration_orm_constraints_and_checkpoint_exclusion(postgres_settings):
    """验证正式数据库迁移与 ORM 一致，并保留第三方 checkpoint 表。

    检查实际约束和索引，以及 Alembic check 不会误报应删除 checkpoint 表。
    """

    async def scenario():
        """创建 checkpoint 后检查 ORM 元数据一致性和数据库唯一约束。"""
        async with runtime(postgres_settings) as (
            database,
            auth,
            _service,
            _graph,
            client,
        ):
            await check_schema(database.engine)
            async with database.engine.connect() as connection:

                def indexes(sync_connection):
                    """通过异步连接桥接 Inspector，仅用于检查数据库实际索引。"""
                    return inspect(sync_connection).get_indexes("conversations")

                actual = await connection.run_sync(indexes)
                assert any(
                    item["name"] == "idx_conversations_user_recent" for item in actual
                )
            username = "race_" + uuid4().hex[:20]
            results = await asyncio.gather(
                *(
                    auth.register(
                        RegisterRequest(username=username, password="password-123")
                    )
                    for _ in range(2)
                ),
                return_exceptions=True,
            )
            assert sum(not isinstance(result, Exception) for result in results) == 1
            assert (
                sum(
                    getattr(result, "error_code", None) is ErrorCode.USERNAME_EXISTS
                    for result in results
                )
                == 1
            )
            _user, headers = await account(auth)
            conversation_id, _ = await send(client, headers)
            from uuid import UUID

            with pytest.raises(IntegrityError):
                async with database.sessions.begin() as session:
                    session.add(
                        ChatTurn(
                            conversation_id=UUID(conversation_id),
                            seq=1,
                            user_content="重复轮次",
                        )
                    )
            with pytest.raises(IntegrityError):
                async with database.sessions.begin() as session:
                    session.add(Conversation(user_id=uuid4(), title="外键必须存在"))

    run_async(scenario())
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "check"],
        cwd=Path(__file__).resolve().parents[1],
        env={
            **os.environ,
            "POSTGRES_DB": postgres_settings.postgres_db,
            "PYTHONIOENCODING": "utf-8",
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_register_login_jwt_claims_and_disabled_account(postgres_settings):
    """验证两类账号的注册登录，以及真实 JWT 的认证边界。

    覆盖必需声明、有效期、签名算法和账号停用状态，测试账号仅写入隔离库。
    """

    async def scenario():
        """走 HTTP 注册与认证，并用已知测试密钥构造错误令牌验证拒绝路径。"""
        async with runtime(postgres_settings) as (
            database,
            _auth,
            _service,
            _graph,
            client,
        ):
            username = "http_" + uuid4().hex[:20]
            body = {
                "username": " " + username.upper() + " ",
                "password": "password-123",
                "role": "super_admin",
            }
            response = await client.post("/api/auth/register", json=body)
            assert response.status_code == 200 and response.json()["code"] == 0
            assert response.json()["data"]["role"] == "super_admin"
            assert "password" not in response.text
            assert (await client.post("/api/auth/register", json=body)).json()[
                "code"
            ] == 20001
            logged = await client.post(
                "/api/auth/login",
                json={"username": username, "password": "password-123"},
            )
            data = logged.json()["data"]
            assert data["expires_in"] == 7200 and data["token_type"] == "bearer"
            headers = {"Authorization": "Bearer " + data["access_token"]}
            assert (await client.get("/api/auth/me", headers=headers)).json()["data"][
                "username"
            ] == username
            for path in ["/api/auth/me", "/api/conversations"]:
                denied = await client.get(path)
                assert (
                    denied.status_code == 401
                    and denied.headers["www-authenticate"] == "Bearer"
                )
            for login_body in [
                {"username": username, "password": "wrong-password"},
                {
                    "username": "missing_" + uuid4().hex[:15],
                    "password": "wrong-password",
                },
            ]:
                denied = await client.post("/api/auth/login", json=login_body)
                assert denied.status_code == 401 and denied.json()["code"] == 40102
            now = datetime.now(UTC)
            payload = {
                "sub": data["user"]["id"],
                "iat": now,
                "exp": now + timedelta(hours=1),
                "iss": "zhizhou",
                "aud": "zhizhou-api",
            }
            bad_claims = [
                {**payload, "exp": now - timedelta(seconds=1)},
                {**payload, "aud": "other"},
                {**payload, "iss": "other"},
                {**payload, "sub": "not-a-uuid"},
                {key: value for key, value in payload.items() if key != "exp"},
            ]
            tokens = [
                jwt.encode(claims, postgres_settings.jwt_secret, algorithm="HS256")
                for claims in bad_claims
            ]
            tokens.extend(
                [
                    jwt.encode(
                        payload, "different-secret-at-least-32-bytes", algorithm="HS256"
                    ),
                    jwt.encode(
                        payload, postgres_settings.jwt_secret, algorithm="HS384"
                    ),
                    "broken-token",
                ]
            )
            for token in tokens:
                assert (
                    await client.get(
                        "/api/auth/me", headers={"Authorization": "Bearer " + token}
                    )
                ).status_code == 401
            async with database.sessions.begin() as session:
                await session.execute(
                    update(User)
                    .where(User.username == username)
                    .values(is_active=False)
                )
            assert (
                await client.get("/api/auth/me", headers=headers)
            ).status_code == 401
            assert (
                await client.post(
                    "/api/auth/login",
                    json={"username": username, "password": "password-123"},
                )
            ).status_code == 401

    run_async(scenario())


@pytest.mark.parametrize(
    "owner_role,other_role", [("user", "super_admin"), ("super_admin", "user")]
)
def test_auto_creation_public_history_ownership_and_soft_delete(
    postgres_settings, owner_role, other_role
):
    """验证会话自动创建、历史恢复、所有权隔离与软删除的完整流程。

    使用真实 checkpoint 续聊，核对超级管理员同样不能越权，删除后底层历史仍保留。
    """

    async def scenario():
        """恢复工具过程并检查所有访问入口，确认非法 ID 不会退化为创建。"""
        async with runtime(postgres_settings) as (
            _database,
            auth,
            _service,
            graph,
            client,
        ):
            _owner, headers = await account(auth, owner_role)
            _, foreign = await account(auth, other_role)
            conversation_id, received = await send(client, headers)
            assert received[0][1]["data"]["is_new"] is True
            for _, payload in received:
                assert payload["data"]["conversation_id"] == conversation_id
            detail = (
                await client.get(
                    f"/api/conversations/{conversation_id}", headers=headers
                )
            ).json()["data"]
            turn = detail["items"][0]
            assert (
                turn["status"] == "completed"
                and turn["assistant_content"] == "上海今天晴天，温度 25°C"
            )
            assert [item["event"] for item in turn["public_events"]] == [
                "delta",
                "tool_call",
                "tool_start",
                "tool_end",
            ]
            assert all(
                item["data"]["conversation_id"] == conversation_id
                for item in turn["public_events"]
            )
            _, continued = await send(client, headers, "第二轮", conversation_id)
            assert continued[0][1]["data"]["is_new"] is False
            assert continued[-1][1]["data"]["reply"] == "天气|第二轮"
            assert (await client.get("/api/conversations", headers=foreign)).json()[
                "data"
            ]["items"] == []
            for method, path, body in [
                ("GET", f"/api/conversations/{conversation_id}", None),
                ("DELETE", f"/api/conversations/{conversation_id}", None),
                (
                    "POST",
                    "/api/chat",
                    {"message": "越权", "conversation_id": conversation_id},
                ),
            ]:
                response = await client.request(
                    method, path, headers=foreign, json=body
                )
                assert response.status_code == 404 and response.json()["code"] == 40401
            assert (
                await client.post(
                    "/api/chat",
                    headers=headers,
                    json={"message": "不能创建", "conversation_id": str(uuid4())},
                )
            ).status_code == 404
            assert (
                await client.post(
                    "/api/chat",
                    headers=headers,
                    json={"message": "旧协议", "thread_id": conversation_id},
                )
            ).status_code == 422
            assert (
                await client.delete(
                    f"/api/conversations/{conversation_id}", headers=headers
                )
            ).json()["code"] == 0
            assert (
                await client.delete(
                    f"/api/conversations/{conversation_id}", headers=headers
                )
            ).json()["code"] == 0
            assert (
                await client.get(
                    f"/api/conversations/{conversation_id}", headers=headers
                )
            ).status_code == 404
            assert (
                await client.post(
                    "/api/chat",
                    headers=headers,
                    json={"message": "删除后续聊", "conversation_id": conversation_id},
                )
            ).status_code == 404
            assert (await client.get("/api/conversations", headers=headers)).json()[
                "data"
            ]["items"] == []
            snapshot = await graph.aget_state(
                {"configurable": {"thread_id": checkpoint_key(conversation_id)}}
            )
            assert snapshot.values["messages"][-1].text == "天气|第二轮"

    run_async(scenario())


def test_recent_and_history_cursors_ties_scope_and_invalid_values(postgres_settings):
    """验证会话目录和历史的游标分页不会遗漏同时间记录或突破归属范围。

    检查历史向前读取但批内正序展示，并拒绝跨用户、跨会话及非法游标。
    """

    async def scenario():
        """构造四个目录及五轮历史，分批读取并验证结束游标和错误边界。"""
        async with runtime(postgres_settings) as (
            database,
            auth,
            _service,
            _graph,
            client,
        ):
            user, headers = await account(auth)
            _, foreign = await account(auth)
            ids = [
                (await send(client, headers, f"输入{index}"))[0] for index in range(4)
            ]
            async with database.sessions.begin() as session:
                await session.execute(
                    update(Conversation)
                    .where(Conversation.user_id == user.id)
                    .values(last_message_at=datetime(2026, 1, 1, tzinfo=UTC))
                )
            first = (
                await client.get("/api/conversations?limit=2", headers=headers)
            ).json()["data"]
            second = (
                await client.get(
                    "/api/conversations",
                    params={"limit": 2, "cursor": first["next_cursor"]},
                    headers=headers,
                )
            ).json()["data"]
            found = [
                item["conversation_id"] for item in first["items"] + second["items"]
            ]
            assert found == sorted(ids, reverse=True) and second["next_cursor"] is None
            assert "total" not in first and "page" not in first
            assert (
                await client.get(
                    "/api/conversations",
                    params={"cursor": first["next_cursor"]},
                    headers=foreign,
                )
            ).status_code == 422
            conversation_id = ids[0]
            for index in range(4):
                await send(client, headers, f"继续{index}", conversation_id)
            cursor = None
            batches = []
            while True:
                params = {"limit": 2}
                if cursor:
                    params["cursor"] = cursor
                data = (
                    await client.get(
                        f"/api/conversations/{conversation_id}",
                        headers=headers,
                        params=params,
                    )
                ).json()["data"]
                batches.append([item["seq"] for item in data["items"]])
                cursor = data["next_cursor"]
                if len(batches) == 1:
                    assert (
                        await client.get(
                            f"/api/conversations/{ids[1]}",
                            headers=headers,
                            params={"cursor": cursor},
                        )
                    ).status_code == 422
                if cursor is None:
                    break
            assert batches == [[4, 5], [2, 3], [1]]
            for params in [
                {"limit": 0},
                {"limit": 101},
                {"cursor": "!"},
                {"cursor": ""},
            ]:
                assert (
                    await client.get(
                        "/api/conversations", headers=headers, params=params
                    )
                ).status_code == 422
                assert (
                    await client.get(
                        f"/api/conversations/{conversation_id}",
                        headers=headers,
                        params=params,
                    )
                ).status_code == 422

    run_async(scenario())


def test_cross_connection_busy_delete_recovery_and_parallel_conversations(
    postgres_settings,
):
    """验证跨连接会话锁能协调生成、删除和遗留轮次恢复。

    独立服务连接竞争同一锁时互斥，不同会话仍可并发；读取不能误中断
    活跃生成，执行者释放锁后才允许恢复遗留运行状态。
    """

    async def scenario():
        """显式持有上下文模拟生成，检查 409、跨会话并发和启动恢复行为。"""
        async with runtime(postgres_settings) as (
            database,
            auth,
            service,
            _graph,
            client,
        ):
            user, headers = await account(auth)
            other_service = ConversationService(database)
            async with service.prepare(user.id, "正在生成", None) as prepared:
                conversation_id = prepared.conversation_id
                with pytest.raises(RequestError) as error:
                    async with other_service.prepare(
                        user.id, "重复生成", conversation_id
                    ):
                        pytest.fail("同会话不应获得第二把执行锁")
                assert error.value.error_code is ErrorCode.CONVERSATION_BUSY
                assert (
                    await client.post(
                        "/api/chat",
                        headers=headers,
                        json={
                            "message": "冲突",
                            "conversation_id": str(conversation_id),
                        },
                    )
                ).status_code == 409
                assert (
                    await client.delete(
                        f"/api/conversations/{conversation_id}", headers=headers
                    )
                ).status_code == 409
                content = await other_service.content(
                    user.id, conversation_id, 20, None
                )
                assert content.items[0].status == "running"
                await other_service.recover()
                assert (
                    await other_service.content(user.id, conversation_id, 20, None)
                ).items[0].status == "running"
                async with other_service.prepare(user.id, "另一个会话", None) as other:
                    assert other.conversation_id != conversation_id
            assert (await service.content(user.id, conversation_id, 20, None)).items[
                0
            ].status == "interrupted"
            async with database.sessions.begin() as session:
                await session.execute(
                    update(ChatTurn)
                    .where(ChatTurn.id == prepared.turn_id)
                    .values(status="running", finished_at=None)
                )
            await service.recover()
            assert (await service.content(user.id, conversation_id, 20, None)).items[
                0
            ].status == "interrupted"

    run_async(scenario())


def test_cancellation_persists_partial_history_and_releases_lock(postgres_settings):
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

    async def scenario():
        """取消正在执行的消费任务，随后从真实数据库检查状态与片段。"""
        entered, cleaned, visible = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async with runtime(
            postgres_settings, PausedModel(entered=entered, cleaned=cleaned)
        ) as (_database, auth, service, graph, _client):
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

    run_async(asyncio.wait_for(scenario(), 15))


def test_final_commit_failure_never_sends_done(postgres_settings, monkeypatch):
    """验证最终业务提交失败时不能向客户端交付成功确认。

    即使 checkpoint 已保存，HTTP 也只能发送 error，业务历史不能标记完成。
    """

    async def scenario():
        """仅使最终提交失败，失败状态仍可正常写入，以检查完成边界。"""
        async with runtime(postgres_settings) as (
            _database,
            auth,
            service,
            _graph,
            client,
        ):
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

    run_async(scenario())
