"""测试应用装配：每例独立创建 FastAPI，复用正式路由与异常处理约定。"""

from fastapi import FastAPI

from app.api.exception_handlers import ERROR_RESPONSES, register_exception_handlers
from app.api.router import api_router


def make_app(*, lifespan=None, agent=None, conversations=None, auth=None, model_config=None, files=None) -> FastAPI:
    """创建独立应用并注入本例资源，调用方负责管理资源的异步生命周期。

    lifespan 测试传入正式 lifespan，由它管理 state；其他测试通过参数提供
    已创建的服务，避免修改正式应用单例及其他用例的依赖覆盖。
    """
    app = FastAPI(title="知舟聊天 API", lifespan=lifespan, responses=ERROR_RESPONSES)
    register_exception_handlers(app)
    app.include_router(api_router)
    for name, value in (
        ("chat_agent", agent),
        ("conversation_service", conversations),
        ("auth_service", auth),
        ("model_config_service", model_config),
        ("file_service", files),
    ):
        if value is not None:
            setattr(app.state, name, value)
    return app
