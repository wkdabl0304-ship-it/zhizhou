"""生命周期替身装配：独立应用执行正式 lifespan，外部资源可观察且可替换。"""

import importlib
from contextlib import asynccontextmanager
from dataclasses import dataclass
from unittest.mock import AsyncMock, Mock
from uuid import UUID

from fastapi import FastAPI

from app.api.dependencies import get_current_user
from app.core.settings import LoggingSettings
from tests.support.apps import make_app
from tests.support.fakes.chat import GraphStub
from tests.support.fakes.services import A, MemoryConversationService


@dataclass
class FakeRuntime:
    """保存本例应用、图替身及资源事件，避免用位置元组隐含资源意义。"""

    app: FastAPI
    graph: GraphStub
    events: list[str]


def make_runtime(monkeypatch) -> FakeRuntime:
    """提供独立应用执行正式生命周期，替身修改由 monkeypatch 自动撤销。"""
    main = importlib.import_module("app.main")
    graph, events = GraphStub(), []
    settings, saver = Mock(model_config_encryption_key="test-only"), object()

    @asynccontextmanager
    async def business_database(actual):
        """提供业务数据库占位对象，使正式 lifespan 无需连接外部数据库。"""
        assert actual is settings
        yield object()

    def current_user():
        """为传输场景提供已认证用户，真实认证由 PostgreSQL 用例验证。"""
        return Mock(id=UUID(A))

    def load_settings():
        """返回本例配置占位对象，以核对初始化各阶段使用同一配置。"""
        return settings

    @asynccontextmanager
    async def open_checkpointer(actual):
        """提供保存器占位对象并记录进入与退出，验证失败时仍释放资源。"""
        assert actual is settings
        events.append("open")
        try:
            yield saver
        finally:
            events.append("close")

    @asynccontextmanager
    async def open_files(database, root):
        """替代文件外部资源边界；正式磁盘及清理生命周期由文件专项验证。"""
        yield Mock()

    def configured_agent(actual_saver, tools):
        """检查运行装配依赖后返回图执行器，协议与数据库在独立用例验证。"""
        from app.agents.agent import ChatAgent
        assert actual_saver is saver
        assert [tool.name for tool in tools] == ["get_weather"]
        events.append("build")
        return ChatAgent(graph)

    # 只替换本例使用的入口函数，不替换全局 logging.dictConfig。
    monkeypatch.setattr(main, "load_logging_settings", LoggingSettings)
    monkeypatch.setattr(main, "configure_logging", Mock())
    monkeypatch.setattr(main, "open_business_database", business_database)
    monkeypatch.setattr(main, "AuthService", Mock(return_value=Mock(initialize=AsyncMock())))
    monkeypatch.setattr(main, "ConversationService", MemoryConversationService)
    monkeypatch.setattr(main, "load_settings", load_settings)
    monkeypatch.setattr(main, "ModelConfigService", Mock())
    monkeypatch.setattr(main, "open_checkpointer", open_checkpointer)
    monkeypatch.setattr(main, "open_file_service", open_files)
    monkeypatch.setattr(main, "ConfiguredChatAgent", configured_agent)
    app = make_app(lifespan=main.lifespan)
    app.dependency_overrides[get_current_user] = current_user
    return FakeRuntime(app=app, graph=graph, events=events)
