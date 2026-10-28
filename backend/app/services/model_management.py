"""模型管理的已授权业务入口；底层配置服务仅供本服务、可信初始化和运行时快照使用。"""

from collections.abc import Awaitable, Callable
from typing import Any

from app.llm.models.catalog import list_models
from app.llm.providers.endpoints import list_providers
from app.models import User
from app.services.authorization import AuthorizationService
from app.services.model_config import ModelConfigService


class ModelManagementService:
    """在模型配置操作前统一检查权限，管理变更与撤权串行，外部模型等待不持管理锁。"""

    def __init__(self, configuration: ModelConfigService):
        """复用底层配置与授权服务，不创建新的模型客户端或数据库引擎。"""
        self.configuration = configuration
        self.authorization = AuthorizationService(configuration.database)

    async def execute[T](self, actor: User, operation: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
        """运行允许的模型管理操作，明确方法白名单防止传入任意函数绕过业务边界。"""
        allowed = {
            self.configuration.list_provider_configurations, self.configuration.get_provider_configuration,
            self.configuration.create_provider_configuration, self.configuration.patch_provider_configuration,
            self.configuration.delete_provider_configuration, self.configuration.list_models,
            self.configuration.get_model, self.configuration.create_model, self.configuration.patch_model,
            self.configuration.delete_model, self.configuration.get_default, self.configuration.set_default,
            self.configuration.test_model,
        }
        if operation not in allowed:
            raise ValueError("不支持的模型管理操作")
        if operation == self.configuration.test_model:
            # 测试获准开始后允许完成，模型调用不占用管理事务；快照仍由配置服务单独读取。
            async with self.authorization.transaction(actor, "model:manage", shared=True):
                pass
            return await operation(*args, **kwargs)
        async with self.authorization.transaction(actor, "model:manage") as session:
            return await operation(*args, session=session, **kwargs)

    async def options(self, actor: User):
        """返回普通用户可用的模型选择，不开放供应商端点或凭据管理信息。"""
        async with self.authorization.transaction(actor, "model:use", shared=True) as session:
            return await self.configuration.selections.options(session=session)

    async def catalog(self, actor: User, *, providers: bool = False, provider=None, api_format=None):
        """向有模型管理权限的用户提供内置供应商或模型目录。"""
        async with self.authorization.transaction(actor, "model:manage", shared=True):
            return list_providers() if providers else list_models(provider, api_format)
