"""受限推理策略：验证方案开放范围、解析默认值并校验会话具体选择，不访问数据库。"""

from pydantic import TypeAdapter

from app.llm.models.catalog import CATALOG
from app.llm.models.policy import resolve_parameters
from app.schemas.model_config import ApiFormat, ModelCreate, Provider
from app.schemas.model_selection import ConcreteReasoning

_concrete = TypeAdapter(ConcreteReasoning)


def concrete_reasoning(body: ModelCreate, api_format: ApiFormat) -> ConcreteReasoning:
    """将方案默认推理解析为具体值，供固定校验、聊天选项和执行快照共用。"""
    value = body.reasoning.model_dump()
    if body.reasoning.mode == "default":
        value = CATALOG[body.catalog_model_id].describe(api_format)["reasoning"]["default"]
    return _concrete.validate_python(value)


def require_allowed(body: ModelCreate, default: ConcreteReasoning, selected: ConcreteReasoning) -> None:
    """拒绝固定值覆盖或范围外的具体推理选择，失败时抛出 ValueError。"""
    policy = body.reasoning_policy
    if policy.mode == "fixed":
        if selected != default:
            raise ValueError("推理值必须与固定配置一致")
        return
    if selected.mode not in policy.allowed_modes:
        raise ValueError("推理方式未开放")
    if selected.mode == "effort" and selected.effort not in policy.effort_options:
        raise ValueError("推理档位未开放")
    if selected.mode == "budget" and (
        policy.budget is None or not policy.budget.min <= selected.budget_tokens <= policy.budget.max
    ):
        raise ValueError("思考预算超出开放范围")


def validate_policy(provider: Provider, api_format: ApiFormat, body: ModelCreate):
    """验证完整方案及开放范围，返回目录项和默认调用参数。

    每种开放方式和预算两端都走现有原生参数校验，避免开放超过模型、协议或
    输出上限的能力；默认推理也必须落在开放范围内。不会静默裁剪无效配置。
    """
    spec, parameters = resolve_parameters(provider, api_format, body.catalog_model_id, body.reasoning, body.max_output_tokens)
    default = concrete_reasoning(body, api_format)
    policy = body.reasoning_policy
    if policy.mode == "selectable":
        capabilities = spec.describe(api_format)["reasoning"]
        if not set(policy.allowed_modes) <= set(capabilities["allowed_modes"]):
            raise ValueError("开放的推理方式超出模型能力")
        candidates = []
        if "off" in policy.allowed_modes:
            candidates.append({"mode": "off"})
        candidates.extend({"mode": "effort", "effort": effort} for effort in policy.effort_options)
        if policy.budget is not None:
            candidates.extend({"mode": "budget", "budget_tokens": value} for value in (policy.budget.min, policy.budget.max))
        for candidate in candidates:
            resolve_parameters(provider, api_format, body.catalog_model_id, _concrete.validate_python(candidate), body.max_output_tokens)
    require_allowed(body, default, default)
    return spec, parameters
