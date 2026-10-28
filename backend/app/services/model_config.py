"""模型配置业务：管理加密凭据、乐观版本、引用约束和一致的每轮执行快照。"""

import asyncio
from contextlib import aclosing
from time import perf_counter
from uuid import UUID

from langchain_core.messages import HumanMessage
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import BusinessError, RequestError
from app.db.business import BusinessDatabase, session_scope
from app.llm.models.catalog import CATALOG
from app.llm.providers.clients import open_model
from app.llm.providers.endpoints import resolve_endpoint
from app.llm.providers.failures import ProviderFailure
from app.llm.secrets import SecretBox
from app.llm.types import ModelSnapshot
from app.models import ModelConfiguration, ProviderConfiguration
from app.repositories import model_config as repository
from app.schemas.model_config import (
    ProviderConfigurationCreate, ProviderConfigurationInfo, ProviderConfigurationPatch, DefaultInfo, DefaultUpdate,
    EndpointConfig, ModelCreate, ModelInfo, ModelPatch, ModelTestResult, CatalogModelInfo,
)
from app.services.model_selection import ModelSelectionService, validate_configuration


def require_version(actual: int, expected: int) -> None:
    """拒绝过期修改，防止其他用户已保存的配置被静默覆盖。"""
    if actual != expected:
        raise RequestError(ErrorCode.MODEL_VERSION_CONFLICT)


def provider_info(row: ProviderConfiguration) -> ProviderConfigurationInfo:
    """返回公开供应商配置，把百炼旧地域数据转换成等价地址，读取不写库或变更版本。"""
    info = ProviderConfigurationInfo.model_validate(row)
    if info.provider == "bailian":
        address = resolve_endpoint(info.provider, info.api_format, info.endpoint_config)
        return info.model_copy(update={"endpoint_config": EndpointConfig(base_url=address)})
    return info


def validate_model(provider_configuration: ProviderConfiguration, body: ModelCreate):
    """验证供应商配置与模型参数组合，返回可用于客户端的具体参数。"""
    try:
        return validate_configuration(provider_configuration, body)
    except ValueError:
        raise RequestError(ErrorCode.INVALID_ARGUMENT) from None


def model_info(model: ModelConfiguration, provider_configuration: ProviderConfiguration) -> ModelInfo:
    """构建配置详情并标记当前目录可用性，失效目录项仍可读取、修改或删除。"""
    spec = CATALOG.get(model.catalog_model_id)
    info = ModelInfo.model_validate(model)
    available = True
    try:
        validate_model(provider_configuration, ModelCreate.model_validate(model))
    except RequestError:
        available = False
    return info.model_copy(update={"catalog": CatalogModelInfo.model_validate(spec.describe(provider_configuration.api_format)) if spec else None,
                                   "available": available,
                                   "selectable": available and model.enabled and provider_configuration.enabled})


class ModelConfigService:
    """维护内部配置存储及运行时快照；对外管理必须经过 ModelManagementService。

    本类供已授权入口、可信初始化和测试装配使用，不作为 Agent 工具的授权入口。
    管理方法的 session 参数只供已授权入口复用事务；省略时使用独立短事务。
    借用事务不自行提交或关闭，避免嵌套连接耗尽池；测试和聊天不持配置写锁。
    """

    def __init__(self, database: BusinessDatabase, encryption_key: str, *, model_opener=open_model):
        """绑定数据库、部署加密主密钥与可替换模型边界，不主动访问供应商。"""
        self.database = database
        self.secrets = SecretBox(encryption_key)
        self.selections = ModelSelectionService(database, self.secrets)
        self.model_opener = model_opener

    async def list_provider_configurations(self, *, session: AsyncSession | None = None) -> list[ProviderConfigurationInfo]:
        """返回所有供应商配置的安全展示字段，不序列化 ORM 凭据列。"""
        async with session_scope(self.database, session) as session:
            return [provider_info(row) for row in await repository.provider_configurations(session)]

    async def get_provider_configuration(self, provider_configuration_id: UUID, *, session: AsyncSession | None = None) -> ProviderConfigurationInfo:
        """读取指定供应商配置，不存在时返回独立资源错误。"""
        async with session_scope(self.database, session) as session:
            row = await repository.provider_configuration(session, provider_configuration_id)
            if row is None:
                raise RequestError(ErrorCode.PROVIDER_CONFIGURATION_NOT_FOUND)
            return provider_info(row)

    async def create_provider_configuration(self, body: ProviderConfigurationCreate, *, session: AsyncSession | None = None) -> ProviderConfigurationInfo:
        """验证官方端点后加密保存供应商配置，不进行真实上游测试。"""
        try:
            address = resolve_endpoint(body.provider, body.api_format, body.endpoint_config)
            if body.provider == "bailian":
                body = body.model_copy(update={"endpoint_config": EndpointConfig(base_url=address)})
        except ValueError:
            raise RequestError(ErrorCode.INVALID_ARGUMENT) from None
        ciphertext = self.secrets.encrypt(body.api_key)
        async with session_scope(self.database, session, write=True) as session:
            await repository.settings(session, lock=True)
            row = ProviderConfiguration(**body.model_dump(exclude={"api_key"}, exclude_none=True), api_key_ciphertext=ciphertext)
            session.add(row)
            await session.flush()
            return provider_info(row)

    async def patch_provider_configuration(self, provider_configuration_id: UUID, patch: ProviderConfigurationPatch, *, session: AsyncSession | None = None) -> ProviderConfigurationInfo:
        """按版本更新供应商配置，端点或格式变化时校验关联方案，不兼容更新整体回滚。"""
        async with session_scope(self.database, session, write=True) as session:
            await repository.settings(session, lock=True)
            row = await repository.provider_configuration(session, provider_configuration_id)
            if row is None:
                raise RequestError(ErrorCode.PROVIDER_CONFIGURATION_NOT_FOUND)
            require_version(row.version, patch.version)
            changes = patch.model_dump(exclude_unset=True, exclude={"version"})
            if not changes or any(value is None for value in changes.values()):
                raise RequestError(ErrorCode.INVALID_ARGUMENT)
            values = provider_info(row).model_dump(exclude={"id", "version", "created_at", "updated_at", "api_key_configured"})
            values.update({key: value for key, value in changes.items() if key != "api_key"})
            try:
                # 用正式创建输入复用名称和凭据校验，密钥不从响应掩码取回。
                validated = ProviderConfigurationCreate(**values, api_key=patch.api_key if "api_key" in changes else "unchanged")
                address = resolve_endpoint(validated.provider, validated.api_format, validated.endpoint_config)
                if validated.provider == "bailian":
                    validated = validated.model_copy(update={"endpoint_config": EndpointConfig(base_url=address)})
            except ValueError:
                raise RequestError(ErrorCode.INVALID_ARGUMENT) from None
            for key, value in validated.model_dump(exclude={"api_key"}, exclude_none=True).items():
                setattr(row, key, value)
            if "api_key" in changes:
                row.api_key_ciphertext = self.secrets.encrypt(validated.api_key)
                row.credential_revision += 1
            # 只在影响参数兼容性时校验关联方案，目录失效不应阻止停用、改名或轮换凭据。
            # 全局设置行锁防止兼容性检查期间插入关联模型。
            if {"api_format", "endpoint_config"} & changes.keys():
                for model, _ in await repository.model_rows(session, provider_configuration_id):
                    try:
                        validate_model(row, ModelCreate.model_validate(model))
                    except RequestError:
                        raise RequestError(ErrorCode.MODEL_CONFIG_IN_USE) from None
            row.version += 1
            await session.flush()
            return provider_info(row)

    async def delete_provider_configuration(self, provider_configuration_id: UUID, version: int, *, session: AsyncSession | None = None) -> None:
        """删除没有关联模型的供应商配置，版本过期或仍被引用时保留原数据。"""
        async with session_scope(self.database, session, write=True) as session:
            await repository.settings(session, lock=True)
            row = await repository.provider_configuration(session, provider_configuration_id)
            if row is None:
                raise RequestError(ErrorCode.PROVIDER_CONFIGURATION_NOT_FOUND)
            require_version(row.version, version)
            if await repository.model_rows(session, provider_configuration_id):
                raise RequestError(ErrorCode.MODEL_CONFIG_IN_USE)
            await session.delete(row)

    async def list_models(self, provider_configuration_id: UUID | None = None, *, session: AsyncSession | None = None) -> list[ModelInfo]:
        """返回可复用模型配置及计算能力，可按供应商配置筛选。"""
        async with session_scope(self.database, session) as session:
            if provider_configuration_id is not None and await repository.provider_configuration(session, provider_configuration_id) is None:
                raise RequestError(ErrorCode.PROVIDER_CONFIGURATION_NOT_FOUND)
            return [model_info(model, provider_configuration) for model, provider_configuration in await repository.model_rows(session, provider_configuration_id)]

    async def get_model(self, model_id: UUID, *, session: AsyncSession | None = None) -> ModelInfo:
        """读取指定模型配置和当前能力，目录停用不妨碍读取历史配置。"""
        async with session_scope(self.database, session) as session:
            row = await repository.model_row(session, model_id)
            if row is None:
                raise RequestError(ErrorCode.MODEL_CONFIGURATION_NOT_FOUND)
            return model_info(*row)

    async def create_model(self, body: ModelCreate, *, session: AsyncSession | None = None) -> ModelInfo:
        """验证模型策略后保存配置，同一模型可以拥有不同推理方案。"""
        async with session_scope(self.database, session, write=True) as session:
            await repository.settings(session, lock=True)
            provider_configuration = await repository.provider_configuration(session, body.provider_configuration_id)
            if provider_configuration is None:
                raise RequestError(ErrorCode.PROVIDER_CONFIGURATION_NOT_FOUND)
            validate_model(provider_configuration, body)
            row = ModelConfiguration(**body.model_dump())
            session.add(row)
            await session.flush()
            return model_info(row, provider_configuration)

    async def patch_model(self, model_id: UUID, patch: ModelPatch, *, session: AsyncSession | None = None) -> ModelInfo:
        """按版本更新模型参数，成功后下一轮聊天自然读取新配置。"""
        async with session_scope(self.database, session, write=True) as session:
            await repository.settings(session, lock=True)
            pair = await repository.model_row(session, model_id)
            if pair is None:
                raise RequestError(ErrorCode.MODEL_CONFIGURATION_NOT_FOUND)
            row, provider_configuration = pair
            require_version(row.version, patch.version)
            changes = patch.model_dump(exclude_unset=True, exclude={"version"})
            if not changes or any(value is None for value in changes.values()):
                raise RequestError(ErrorCode.INVALID_ARGUMENT)
            try:
                validated = ModelCreate.model_validate(ModelCreate.model_validate(row).model_dump() | changes)
            except ValidationError:
                raise RequestError(ErrorCode.INVALID_ARGUMENT) from None
            # 元数据和启停可独立管理；修改运行参数才需要重新满足完整模型策略。
            if {"catalog_model_id", "reasoning", "reasoning_policy", "max_output_tokens"} & changes.keys():
                validate_model(provider_configuration, validated)
            for key, value in validated.model_dump().items():
                setattr(row, key, value)
            row.version += 1
            await session.flush()
            return model_info(row, provider_configuration)

    async def delete_model(self, model_id: UUID, version: int, *, session: AsyncSession | None = None) -> None:
        """删除非默认模型配置，默认引用必须先显式切换或清除。"""
        async with session_scope(self.database, session, write=True) as session:
            settings = await repository.settings(session, lock=True)
            pair = await repository.model_row(session, model_id)
            if pair is None:
                raise RequestError(ErrorCode.MODEL_CONFIGURATION_NOT_FOUND)
            row, _ = pair
            require_version(row.version, version)
            if settings.model_configuration_id == model_id:
                raise RequestError(ErrorCode.MODEL_CONFIG_IN_USE)
            await session.delete(row)

    async def get_default(self, *, session: AsyncSession | None = None) -> DefaultInfo:
        """读取默认引用及可选模型概要，空默认是正常的首次配置状态。"""
        async with session_scope(self.database, session) as session:
            settings, model, provider_configuration = await repository.default_row(session)
            return DefaultInfo.model_validate(settings).model_copy(update={"model": model_info(model, provider_configuration) if model else None})

    async def set_default(self, body: DefaultUpdate, *, session: AsyncSession | None = None) -> DefaultInfo:
        """原子切换或清空全局默认，只做本地有效性校验，不触发上游调用。"""
        async with session_scope(self.database, session, write=True) as session:
            settings = await repository.settings(session, lock=True)
            require_version(settings.version, body.version)
            info = None
            if body.model_configuration_id is not None:
                pair = await repository.model_row(session, body.model_configuration_id)
                if pair is None:
                    raise RequestError(ErrorCode.MODEL_CONFIGURATION_NOT_FOUND)
                model, provider_configuration = pair
                validate_model(provider_configuration, ModelCreate.model_validate(model))
                info = model_info(model, provider_configuration)
                if not info.selectable:
                    raise RequestError(ErrorCode.MODEL_SELECTION_UNAVAILABLE)
            settings.model_configuration_id = body.model_configuration_id
            settings.version += 1
            await session.flush()
            return DefaultInfo.model_validate(settings).model_copy(update={"model": info})

    async def snapshot(self, model_id: UUID | None = None, *, allow_disabled: bool = False) -> ModelSnapshot:
        """以单条联表查询固定执行版本和凭据，结束读事务后再访问模型服务。"""
        async with self.database.sessions() as session:
            return await self.selections.snapshot(session, model_id=model_id, allow_disabled=allow_disabled)

    async def test_model(self, model_id: UUID) -> ModelTestResult:
        """主动执行一次固定短文本流，不创建会话、不调用业务工具、不持数据库锁。"""
        snapshot = await self.snapshot(model_id, allow_disabled=True)
        started = perf_counter()
        try:
            async with asyncio.timeout(120), self.model_opener(snapshot) as model:
                text = ""
                async with aclosing(model.astream([HumanMessage(content="请只回复：测试成功")])) as stream:
                    async for chunk in stream:
                        text += str(chunk.text)
                if not text.strip():
                    raise BusinessError(ErrorCode.MODEL_TEST_FAILED)
        except ProviderFailure as error:
            raise BusinessError(error.error_code) from None
        except TimeoutError:
            raise BusinessError(ErrorCode.MODEL_TIMEOUT) from None
        return ModelTestResult(latency_ms=round((perf_counter() - started) * 1000, 2),
                               provider_configuration_version=snapshot.provider_configuration_version, model_version=snapshot.model_version)
