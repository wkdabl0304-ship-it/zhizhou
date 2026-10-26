"""模型配置 API：登录用户共享管理供应商配置、模型方案、默认引用及主动模型测试。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_current_user, get_model_config_service
from app.llm.models.catalog import list_models
from app.llm.providers.endpoints import list_providers
from app.schemas.model_config import (
    ApiFormat, ProviderConfigurationCreate, ProviderConfigurationInfo, ProviderConfigurationPatch, DefaultInfo, DefaultUpdate,
    ModelCreate, ModelInfo, ModelPatch, ModelTestResult, Provider, ProviderInfo, CatalogModelInfo,
)
from app.schemas.response import ApiResponse, success
from app.services.model_config import ModelConfigService
from app.schemas.model_selection import ModelOptions

router = APIRouter(prefix="/model-config", tags=["模型配置"], dependencies=[Depends(get_current_user)])
type Service = Annotated[ModelConfigService, Depends(get_model_config_service)]
type Version = Annotated[int, Query(gt=0)]


@router.get("/options", response_model=ApiResponse[ModelOptions])
async def options(service: Service):
    """返回聊天允许选择的方案、推理范围和有效默认，不访问供应商。"""
    return success(await service.selections.options())


@router.get("/catalog/providers", response_model=ApiResponse[list[ProviderInfo]])
async def providers():
    """返回四家官方供应商、接口格式和可填写的官方端点字段。"""
    return success(list_providers())


@router.get("/catalog/models", response_model=ApiResponse[list[CatalogModelInfo]])
async def catalog(provider: Provider | None = None, api_format: ApiFormat | None = None):
    """返回后端已适配的只读模型目录及对应推理控件，不访问上游模型列表。"""
    return success(list_models(provider, api_format))


@router.get("/provider-configurations", response_model=ApiResponse[list[ProviderConfigurationInfo]])
async def provider_configurations(service: Service):
    """列出全局供应商配置，不返回任何账号密钥。"""
    return success(await service.list_provider_configurations())


@router.post("/provider-configurations", response_model=ApiResponse[ProviderConfigurationInfo])
async def create_provider_configuration(body: ProviderConfigurationCreate, service: Service):
    """创建官方供应商配置，仅执行本地校验和加密存储。"""
    return success(await service.create_provider_configuration(body))


@router.get("/provider-configurations/{provider_configuration_id}", response_model=ApiResponse[ProviderConfigurationInfo])
async def provider_configuration(provider_configuration_id: UUID, service: Service):
    """读取指定供应商配置的安全展示字段。"""
    return success(await service.get_provider_configuration(provider_configuration_id))


@router.patch("/provider-configurations/{provider_configuration_id}", response_model=ApiResponse[ProviderConfigurationInfo])
async def patch_provider_configuration(provider_configuration_id: UUID, body: ProviderConfigurationPatch, service: Service):
    """按读取时版本修改供应商配置，省略密钥表示保留已有凭据。"""
    return success(await service.patch_provider_configuration(provider_configuration_id, body))


@router.delete("/provider-configurations/{provider_configuration_id}", response_model=ApiResponse[None])
async def delete_provider_configuration(provider_configuration_id: UUID, version: Version, service: Service):
    """删除未被模型配置引用且版本仍一致的供应商配置。"""
    await service.delete_provider_configuration(provider_configuration_id, version)
    return success(None)


@router.get("/models", response_model=ApiResponse[list[ModelInfo]])
async def models(service: Service, provider_configuration_id: UUID | None = None):
    """列出用户保存的模型方案，可按供应商配置筛选。"""
    return success(await service.list_models(provider_configuration_id))


@router.post("/models", response_model=ApiResponse[ModelInfo])
async def create_model(body: ModelCreate, service: Service):
    """从内置目录创建模型方案，并校验协议、推理档位和输出预算。"""
    return success(await service.create_model(body))


@router.get("/models/{model_id}", response_model=ApiResponse[ModelInfo])
async def model(model_id: UUID, service: Service):
    """读取模型方案及由当前目录计算的能力。"""
    return success(await service.get_model(model_id))


@router.patch("/models/{model_id}", response_model=ApiResponse[ModelInfo])
async def patch_model(model_id: UUID, body: ModelPatch, service: Service):
    """按版本修改模型方案，相关会话在下一轮重新校验选择与推理限制。"""
    return success(await service.patch_model(model_id, body))


@router.delete("/models/{model_id}", response_model=ApiResponse[None])
async def delete_model(model_id: UUID, version: Version, service: Service):
    """删除非默认模型方案，当前默认必须先切换或清除。"""
    await service.delete_model(model_id, version)
    return success(None)


@router.get("/default", response_model=ApiResponse[DefaultInfo])
async def get_default(service: Service):
    """读取全局默认引用；未配置时返回正常的空引用。"""
    return success(await service.get_default())


@router.put("/default", response_model=ApiResponse[DefaultInfo])
async def set_default(body: DefaultUpdate, service: Service):
    """按版本切换或清除默认模型，不隐式发起付费测试调用。"""
    return success(await service.set_default(body))


@router.post("/models/{model_id}/test", response_model=ApiResponse[ModelTestResult])
async def test_model(model_id: UUID, service: Service):
    """主动发起一次短文本流测试，不创建会话、不验证或调用业务工具。"""
    return success(await service.test_model(model_id))
