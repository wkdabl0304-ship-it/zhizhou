"""API 请求的公共依赖，从应用生命周期中取得已初始化的业务资源。

不导入 main，也不在请求期间创建模型或数据库连接，避免循环依赖和重复初始化。
"""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.llm.runtime import ConfiguredChatAgent
from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import RequestError
from app.models import User
from app.services.auth import AuthService
from app.services.conversations import ConversationService
from app.services.model_config import ModelConfigService
from app.services.departments import DepartmentService
from app.services.users import UserManagementService
from app.services.model_management import ModelManagementService

bearer = HTTPBearer(auto_error=False)


def get_model_config_service(request: Request) -> ModelConfigService:
    """取得内部配置资源；对外管理必须经 ModelManagementService 授权后调用。"""
    return request.app.state.model_config_service


def get_model_management_service(request: Request) -> ModelManagementService:
    """为模型接口包装已授权业务入口，复用底层配置服务及其连接工厂。"""
    return ModelManagementService(get_model_config_service(request))


def get_user_management_service(request: Request) -> UserManagementService:
    """为用户管理接口提供轻量服务，复用认证服务的数据库资源。"""
    return UserManagementService(get_auth_service(request).database)


def get_department_service(request: Request) -> DepartmentService:
    """为部门接口提供轻量服务，不在依赖解析期间创建连接或事务。"""
    return DepartmentService(get_auth_service(request).database)


def get_auth_service(request: Request) -> AuthService:
    """为接口注入应用共享的认证服务。

    从 request.app.state 取回启动时创建的实例，不在请求中重建密码工具
    或数据库引擎；应用资源缺失时异常继续向外传播。
    """
    return request.app.state.auth_service


def get_conversation_service(request: Request) -> ConversationService:
    """为接口注入应用共享的会话业务服务。

    服务从 request.app.state 取得，可跨请求复用；各次操作自行创建短事务，
    此依赖不创建或关闭数据库 Session。
    """
    return request.app.state.conversation_service


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    """识别当前请求的已认证用户，供业务接口判断资源归属。

    credentials 由 HTTPBearer 提取，缺少凭证时抛出 UNAUTHENTICATED；
    认证服务验证 JWT 并查询最新账号状态。取得用户并不代表已授权访问
    任意会话，后续仍须执行所有权检查。
    """
    if credentials is None:
        raise RequestError(ErrorCode.UNAUTHENTICATED)
    return await auth.authenticate(credentials.credentials)


def get_chat_agent(request: Request) -> ConfiguredChatAgent:
    """取得共享聊天执行器，具体供应商客户端在每轮持有配置快照后创建。

    request 由 FastAPI 提供，其 app.state 中的实例在应用退出时释放。
    本函数不创建或关闭资源；若生命周期没有正确初始化，异常向外传播，
    由全局系统错误处理器兜底。测试可覆盖此依赖以注入独立替身。
    """
    return request.app.state.chat_agent
