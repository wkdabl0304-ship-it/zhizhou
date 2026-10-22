"""API 请求的公共依赖，从应用生命周期中取得已初始化的业务资源。

不导入 main，也不在请求期间创建模型或数据库连接，避免循环依赖和重复初始化。
"""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.agents.agent import ChatAgent
from app.errors.codes import ErrorCode
from app.errors.exceptions import RequestError
from app.models import User
from app.services.auth import AuthService
from app.services.conversations import ConversationService

bearer = HTTPBearer(auto_error=False)


def get_auth_service(request: Request) -> AuthService:
    """取得生命周期内创建的认证服务，不在请求中重建密码工具或引擎。"""
    return request.app.state.auth_service


def get_conversation_service(request: Request) -> ConversationService:
    """取得会话服务，其自身仅持有工厂，每次操作都创建独立短事务。"""
    return request.app.state.conversation_service


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    """要求 Bearer JWT 并查询最新账号状态，角色不绕过会话所有权检查。"""
    if credentials is None:
        raise RequestError(ErrorCode.UNAUTHENTICATED)
    return await auth.authenticate(credentials.credentials)


def get_chat_agent(request: Request) -> ChatAgent:
    """返回当前应用启动时创建的 ChatAgent，供接口通过 Depends 注入。

    request 由 FastAPI 提供，其 app.state 中的实例在应用退出时释放。
    本函数不创建或关闭资源；若生命周期没有正确初始化，异常向外传播，
    由全局系统错误处理器兜底。测试可覆盖此依赖以注入独立替身。
    """
    return request.app.state.chat_agent
