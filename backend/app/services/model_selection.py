"""模型选择业务：组装安全选项、批量判断失效原因并生成逐轮执行快照。"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import RequestError, ServiceError
from app.db.business import BusinessDatabase, session_scope
from app.llm.models.policy import resolve_parameters
from app.llm.models.selection import concrete_reasoning, require_allowed, validate_policy
from app.llm.providers.endpoints import resolve_endpoint
from app.llm.secrets import SecretBox
from app.llm.types import ModelSnapshot
from app.models import ModelConfiguration, ProviderConfiguration
from app.repositories import model_config as repository
from app.schemas.model_config import EndpointConfig, ModelCreate
from app.schemas.model_selection import ModelOptions, ModelSelection, SelectableModel, SelectableProvider, SelectionIssue


def validate_configuration(provider: ProviderConfiguration, body: ModelCreate):
    """验证端点和完整模型策略，管理写入与聊天执行共用同一规则。"""
    resolve_endpoint(provider.provider, provider.api_format, EndpointConfig.model_validate(provider.endpoint_config))
    return validate_policy(provider.provider, provider.api_format, body)


def selection_issue(selection: ModelSelection | None, pair) -> SelectionIssue | None:
    """判断保存选择的当前失效原因，缺失方案或范围变化不妨碍读取历史。"""
    if selection is None:
        return None
    if pair is None:
        return "model_deleted"
    model, provider = pair
    if not provider.enabled:
        return "provider_disabled"
    if not model.enabled:
        return "model_disabled"
    try:
        body = ModelCreate.model_validate(model)
        validate_configuration(provider, body)
    except ValueError:
        return "model_unavailable"
    try:
        require_allowed(body, concrete_reasoning(body, provider.api_format), selection.reasoning)
        resolve_parameters(provider.provider, provider.api_format, body.catalog_model_id, selection.reasoning, body.max_output_tokens)
    except ValueError:
        return "reasoning_not_allowed"
    return None


def require_selection(selection: ModelSelection, pair) -> None:
    """把选择失效转换为稳定请求错误，不把缺失模型误报为会话不存在。"""
    issue = selection_issue(selection, pair)
    if issue is not None:
        raise RequestError(ErrorCode.REASONING_NOT_ALLOWED if issue == "reasoning_not_allowed" else ErrorCode.MODEL_SELECTION_UNAVAILABLE)


class ModelSelectionService:
    """独立承担模型读取与执行装配，不将会话状态或资源生命周期混入配置 CRUD。"""

    def __init__(self, database: BusinessDatabase, secrets: SecretBox):
        """复用已有数据库及加密器，不在构造时读取配置或访问供应商。"""
        self.database = database
        self.secrets = secrets

    async def options(self, *, session: AsyncSession | None = None) -> ModelOptions:
        """返回安全选项及默认，可复用授权事务，避免每次读取占用两个池连接。"""
        async with session_scope(self.database, session) as session:
            rows = await repository.option_rows(session)
            providers = {}
            default = None
            for settings, model, provider in rows:
                if model is None or not provider.enabled or not model.enabled:
                    continue
                try:
                    body = ModelCreate.model_validate(model)
                    spec, _ = validate_configuration(provider, body)
                    reasoning = concrete_reasoning(body, provider.api_format)
                except ValueError:
                    continue
                group = providers.setdefault(provider.id, SelectableProvider(
                    provider_configuration_id=provider.id, name=provider.name, provider=provider.provider, models=[]))
                group.models.append(SelectableModel(
                    model_configuration_id=model.id, name=model.name, catalog_model_id=model.catalog_model_id,
                    display_name=spec.display_name,
                    reasoning_control=body.reasoning_policy.model_dump() | {"default": reasoning.model_dump()}))
                if settings.model_configuration_id == model.id:
                    default = ModelSelection(model_configuration_id=model.id, reasoning=reasoning)
            return ModelOptions(default_selection=default, providers=list(providers.values()))

    async def issues(self, session: AsyncSession, conversations) -> dict[UUID, SelectionIssue | None]:
        """批量计算目录或详情的失效原因，空选择无需读取模型配置。"""
        selections = {row.id: ModelSelection.model_validate(row.model_selection) if row.model_selection is not None else None
                      for row in conversations}
        ids = {value.model_configuration_id for value in selections.values() if value is not None}
        pairs = {model.id: (model, provider) for model, provider in await repository.selected_model_rows(session, ids)}
        return {key: selection_issue(value, pairs.get(value.model_configuration_id) if value else None)
                for key, value in selections.items()}

    async def validate(self, session: AsyncSession, selection: ModelSelection) -> None:
        """验证待保存的具体选择，不解密凭据，也不发起模型调用。"""
        require_selection(selection, await repository.model_row(session, selection.model_configuration_id))

    async def snapshot(self, session: AsyncSession, selection: ModelSelection | None = None, *,
                       model_id: UUID | None = None, allow_disabled: bool = False) -> ModelSnapshot:
        """读取并固定本轮模型、版本、凭据和推理参数，返回后不再读取配置。

        默认引用不可用时报 503；明确选择失效时报 422。管理测试可显式允许停用，
        但仍验证模型策略。配置查询时刻作为本轮生效边界，不跨供应商调用持锁。
        """
        uses_default = selection is None and model_id is None
        if uses_default:
            _, model, provider = await repository.default_row(session)
            pair = (model, provider) if model is not None else None
        else:
            pair = await repository.model_row(session, selection.model_configuration_id if selection else model_id)
        if pair is None:
            if uses_default:
                raise ServiceError(ErrorCode.MODEL_NOT_CONFIGURED)
            raise RequestError(ErrorCode.MODEL_SELECTION_UNAVAILABLE if selection else ErrorCode.MODEL_CONFIGURATION_NOT_FOUND)
        model, provider = pair
        if selection is not None:
            require_selection(selection, pair)
        try:
            body = ModelCreate.model_validate(model)
            validate_configuration(provider, body)
            if not allow_disabled and (not model.enabled or not provider.enabled):
                raise ValueError("配置停用")
            reasoning = selection.reasoning if selection else concrete_reasoning(body, provider.api_format)
            _, parameters = resolve_parameters(provider.provider, provider.api_format, body.catalog_model_id, reasoning, body.max_output_tokens)
        except ValueError:
            if uses_default:
                raise ServiceError(ErrorCode.MODEL_NOT_CONFIGURED) from None
            raise RequestError(ErrorCode.MODEL_SELECTION_UNAVAILABLE) from None
        try:
            secret = self.secrets.decrypt(provider.api_key_ciphertext)
        except ValueError:
            raise ServiceError(ErrorCode.MODEL_PROVIDER_FAILED) from None
        return ModelSnapshot(
            provider.id, model.id, provider.version, model.version, provider.credential_revision,
            provider.provider, provider.api_format, model.catalog_model_id,
            resolve_endpoint(provider.provider, provider.api_format, EndpointConfig.model_validate(provider.endpoint_config)),
            parameters, secret, reasoning=reasoning.model_dump())
