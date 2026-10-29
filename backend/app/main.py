"""定义知舟 FastAPI 应用、生命周期和 API 路由装配。

Web 进程由包入口启动；本模块负责启动时组装资源、退出时释放资源，
通过总路由挂载业务接口。具体 HTTP 请求处理与异常转换由 API 层负责。
"""

import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI

from app.llm.runtime import ConfiguredChatAgent
from app.agents.tools.weather import get_weather
from app.api.exception_handlers import ERROR_RESPONSES, register_exception_handlers
from app.api.router import api_router
from app.core.logging import configure_logging
from app.core.settings import load_logging_settings, load_settings
from app.db.business import open_business_database
from app.db.checkpoint import open_checkpointer
from app.services.auth import AuthService
from app.services.conversations import ConversationService
from app.services.conversation_titles import ConversationTitleService
from app.services.model_config import ModelConfigService
from app.services.files.lifecycle import open_file_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """初始化 Web 应用的共享服务，并在应用关闭时释放全部数据库资源。

    依次准备业务数据库、认证和配置服务、会话恢复、checkpoint 与文件服务；
    文件服务验证磁盘并启动清理。全部成功后才接受请求，退出时先撤销
    app.state 中的服务，停止清理任务，再关闭底层异步资源。

    Args:
        app: 当前 FastAPI 实例，共享 Agent、认证与会话服务存放在 app.state 中。

    Yields:
        None: yield 前完成启动，yield 后执行退出清理。

    Raises:
        Exception: 配置、模型或数据库初始化失败时记录原始异常并终止启动。
    """
    configure_logging(load_logging_settings()) # 这里再次配置日志是为了兼容用 uvicorn 启动项目
    # 异步资源栈确保组装失败与正常退出都能等待连接关闭。
    async with AsyncExitStack() as resources:
        try:
            settings = load_settings()
            database = await resources.enter_async_context(open_business_database(settings))
            auth_service = AuthService(database, settings) # 初始化 AuthService
            await auth_service.initialize()
            model_config = ModelConfigService(database, settings.model_config_encryption_key)
            conversation_service = ConversationService(database, model_config=model_config,
                                                       title_generator=ConversationTitleService())
            await conversation_service.recover()
            checkpointer = await resources.enter_async_context(open_checkpointer(settings))
            file_service = await resources.enter_async_context(open_file_service(database, settings.file_storage_root))
            # 启动不创建供应商客户端，无模型配置时仍可登录和完成首次设置。
            app.state.chat_agent = ConfiguredChatAgent(checkpointer, [get_weather])
            app.state.auth_service = auth_service
            app.state.conversation_service = conversation_service
            app.state.model_config_service = model_config
            app.state.file_service = file_service
        except Exception:
            logger.exception("应用启动失败")
            raise
        # 只有所有资源均准备就绪，才开始接受业务请求。
        logger.info("应用启动完成")
        try:
            yield
        finally:
            # 先撤销对外暴露的对象，再关闭其依赖，防止继续使用已关闭连接。
            del app.state.chat_agent
            del app.state.auth_service
            del app.state.conversation_service
            del app.state.model_config_service
            del app.state.file_service
            await resources.aclose()
            logger.info("应用资源已关闭")


app = FastAPI(title="知舟聊天 API", lifespan=lifespan, responses=ERROR_RESPONSES) # responses 让 Swagger 显示错误响应
# 注册异常类型到响应的映射，后续路由不需要各自处理相同异常。
register_exception_handlers(app)
# /api 前缀与业务子路由均在总路由中管理，应用入口只装配一次。
app.include_router(api_router)
