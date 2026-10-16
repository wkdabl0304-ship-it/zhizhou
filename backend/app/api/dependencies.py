"""API 请求的公共依赖，从应用生命周期中取得已初始化的业务资源。

不导入 main，也不在请求期间创建模型或数据库连接，避免循环依赖和重复初始化。
"""

from fastapi import Request

from app.agents.agent import ChatAgent


def get_chat_agent(request: Request) -> ChatAgent:
    """返回当前应用启动时创建的 ChatAgent，供接口通过 Depends 注入。

    request 由 FastAPI 提供，其 app.state 中的实例在应用退出时释放。
    本函数不创建或关闭资源；若生命周期没有正确初始化，异常向外传播，
    由全局系统错误处理器兜底。测试可覆盖此依赖以注入独立替身。
    """
    return request.app.state.chat_agent
