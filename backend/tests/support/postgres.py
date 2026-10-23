"""PostgreSQL 测试支撑：隔离库生命周期、正式后端资源及常用请求操作。"""

import re
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from uuid import uuid4

import anyio
import httpx
import psycopg
from psycopg import sql

from app.agents.agent import ChatAgent
from app.agents.factory import build_agent
from app.agents.tools.weather import get_weather
from app.core.settings import DatabaseSettings, Settings
from app.db.business import BusinessDatabase, open_business_database
from app.db.checkpoint import build_conninfo, open_checkpointer
from app.schemas.auth import LoginRequest, RegisterRequest
from app.services.auth import AuthService
from app.services.conversations import ConversationService
from tests.support.apps import make_app
from tests.support.fakes.chat import StubChatModel
from tests.support.processes import run_python
from tests.support.sse import parse_events


def database_environment(settings: Settings | DatabaseSettings) -> dict[str, str]:
    """生成迁移子进程的完整数据库配置，覆盖父进程与 .env 中的开发库设置。"""
    return {
        "POSTGRES_HOST": settings.postgres_host,
        "POSTGRES_PORT": str(settings.postgres_port),
        "POSTGRES_USER": settings.postgres_user,
        "POSTGRES_PASSWORD": settings.postgres_password,
        "POSTGRES_DB": settings.postgres_db,
    }


def migrate_database(settings: Settings | DatabaseSettings, command="upgrade"):
    """在目标临时库执行正式 Alembic 升级或结构检查，失败时保留诊断输出。"""
    arguments = ("-m", "alembic", "upgrade", "head") if command == "upgrade" else ("-m", "alembic", "check")
    return run_python(*arguments, env_overrides=database_environment(settings))


class TemporaryDatabase:
    """管理本次成功创建的唯一临时库，维护连接始终指向 postgres 数据库。"""

    def __init__(self, base: DatabaseSettings):
        """记录维护连接及随机目标名称，创建成功前不赋予清理权限。"""
        self.maintenance = replace(base, postgres_db="postgres")
        self.name = f"zhizhou_test_{uuid4().hex}"
        self._created_name: str | None = None

    async def create(self) -> Settings:
        """创建本例专属数据库并返回无真实模型凭据的应用配置。

        建库成功后立即登记精确名称；后续配置或迁移失败时仍可清理。
        连接与权限错误直接使测试失败，不转为跳过。
        """
        if self._created_name is not None:
            raise RuntimeError("本例已经创建临时测试库")
        async with await psycopg.AsyncConnection.connect(
            build_conninfo(self.maintenance), autocommit=True, connect_timeout=5
        ) as connection:
            await connection.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(self.name))
            )
            self._created_name = self.name
        return Settings(
            deepseek_api_key="unused-test-key",
            postgres_user=self.maintenance.postgres_user,
            postgres_password=self.maintenance.postgres_password,
            postgres_db=self.name,
            postgres_port=self.maintenance.postgres_port,
            postgres_host=self.maintenance.postgres_host,
            jwt_secret="integration-secret-which-is-at-least-48-bytes-long-for-tests",
        )

    async def drop(self) -> None:
        """仅删除本对象成功创建且名称仍一致的临时库，不清理其他已有库。"""
        if self._created_name is None:
            return
        if self.name != self._created_name or not re.fullmatch(r"zhizhou_test_[0-9a-f]{32}", self.name):
            raise RuntimeError("拒绝清理未经本次创建确认的数据库")
        async with await psycopg.AsyncConnection.connect(
            build_conninfo(self.maintenance), autocommit=True, connect_timeout=5
        ) as connection:
            await connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(self._created_name))
            )
        self._created_name = None


@asynccontextmanager
async def temporary_database(
    base: DatabaseSettings, *, on_created: Callable[[str], None] | None = None,
) -> AsyncIterator[Settings]:
    """提供已迁移的独立临时库，建库后的初始化或用例失败均执行回收。

    调用方必须在退出前关闭业务资源。迁移放入工作线程执行同步子进程，
    避免 Windows Selector 循环不支持异步子进程；清理不受调用方取消影响。
    on_created 在建库成功后、迁移前通知调用方目标库名，供启动器记录强制终止时的排查依据。
    """
    database = TemporaryDatabase(base)
    try:
        settings = await database.create()
        if on_created is not None:
            on_created(settings.postgres_db)
        await anyio.to_thread.run_sync(migrate_database, settings)
        yield settings
    finally:
        with anyio.CancelScope(shield=True):
            await database.drop()


@dataclass
class PostgresRuntime:
    """表示同一循环内创建并关闭的真实数据库、业务服务、图与 HTTP 客户端。"""

    database: BusinessDatabase
    auth: AuthService
    conversations: ConversationService
    graph: object
    client: httpx.AsyncClient


@asynccontextmanager
async def open_runtime(settings: Settings, model=None) -> AsyncIterator[PostgresRuntime]:
    """组装连接临时库的正式后端组件，退出时先关闭客户端再释放数据库资源。"""
    async with (
        open_business_database(settings) as database,
        open_checkpointer(settings) as checkpointer,
    ):
        auth = AuthService(database, settings)
        await auth.initialize()
        conversations = ConversationService(database)
        graph = build_agent(model if model is not None else StubChatModel(), [get_weather], checkpointer)
        app = make_app(agent=ChatAgent(graph), conversations=conversations, auth=auth)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield PostgresRuntime(
                database=database, auth=auth, conversations=conversations,
                graph=graph, client=client,
            )


async def account(auth, role="user"):
    """创建本例专享账号并返回用户及 Bearer 请求头，随机名称避免账号冲突。"""
    username = "u_" + uuid4().hex[:20]
    registered = await auth.register(RegisterRequest(username=username, password="password-with-spaces ", role=role))
    logged = await auth.login(LoginRequest(username=username.upper(), password="password-with-spaces "))
    return registered, {"Authorization": f"Bearer {logged.access_token}"}


async def send(client, headers, message="天气", conversation_id=None):
    """完成一轮正式聊天请求并返回业务 ID 与事件，确认服务器成功完成本轮。"""
    body = {"message": message}
    if conversation_id is not None:
        body["conversation_id"] = str(conversation_id)
    response = await client.post("/api/chat", json=body, headers=headers)
    assert response.status_code == 200, response.text
    received = parse_events(response)
    assert received[0].event == "start" and received[-1].event == "done", response.text
    assert "thread_id" not in response.text
    return received[0].payload["data"]["conversation_id"], received
