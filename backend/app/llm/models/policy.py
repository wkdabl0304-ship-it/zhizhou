"""具体模型参数策略：校验统一业务配置并生成专用 LangChain 客户端参数。"""

from typing import Any

from app.llm.models.catalog import CATALOG, ModelSpec
from app.schemas.model_config import ApiFormat, Provider, Reasoning


def resolve_parameters(
    provider: Provider, api_format: ApiFormat, catalog_model_id: str,
    reasoning: Reasoning, max_output_tokens: int,
) -> tuple[ModelSpec, dict[str, Any]]:
    """生成当前模型可接受的调用参数，拒绝未知模型和不兼容配置。

    参数由 API 数据模型先校验形状，本层统一验证供应商、协议、档位和
    输出预算；返回目录项及客户端构造参数，不创建供应商客户端、不访问数据库。
    """
    spec = CATALOG.get(catalog_model_id)
    if spec is None or not spec.available or spec.provider != provider or api_format not in spec.formats:
        raise ValueError("模型或接口格式不受支持")
    if not 0 < max_output_tokens <= spec.max_output_tokens:
        raise ValueError("输出上限超出模型范围")
    selected = reasoning.model_dump()
    if selected["mode"] == "default":
        selected = spec.describe(api_format)["reasoning"]["default"]
    mode = selected["mode"]
    if mode not in spec.describe(api_format)["reasoning"]["allowed_modes"]:
        raise ValueError("模型不支持该推理方式")
    effort = selected.get("effort")
    if mode == "effort" and effort not in spec.efforts:
        raise ValueError("模型不支持该推理档位")
    budget = selected.get("budget_tokens")
    if mode == "budget":
        minimum = 1024 if provider == "anthropic" else 1
        if not minimum <= budget <= spec.budget_max or (provider == "anthropic" and budget >= max_output_tokens):
            raise ValueError("思考预算与输出上限不兼容")
    parameters: dict[str, Any] = {"model": spec.model_id}
    if provider == "openai":
        if api_format == "responses":
            parameters.update(use_responses_api=True, max_tokens=max_output_tokens,
                              reasoning={"effort": "none" if mode == "off" else effort},
                              store=False, include=["reasoning.encrypted_content"])
        else:
            parameters.update(use_responses_api=False, max_completion_tokens=max_output_tokens,
                              reasoning_effort="none" if mode == "off" else effort)
    elif provider == "deepseek":
        parameters.update(max_tokens=max_output_tokens,
                          extra_body={"thinking": {"type": "disabled" if mode == "off" else "enabled"}})
        if mode == "effort":
            parameters["reasoning_effort"] = effort
    elif provider == "anthropic":
        parameters["max_tokens"] = max_output_tokens
        if mode == "off":
            parameters["thinking"] = {"type": "disabled"}
            if spec.efforts:
                parameters["output_config"] = {"effort": "low"}
        elif mode == "budget":
            parameters["thinking"] = {"type": "enabled", "budget_tokens": budget}
        else:
            parameters.update(thinking={"type": "adaptive"}, output_config={"effort": effort})
    else:
        parameters.update(max_tokens=max_output_tokens, use_responses_api=False,
                          enable_thinking=mode != "off")
        if mode == "effort":
            parameters["reasoning_effort"] = effort
        elif mode == "budget":
            parameters["thinking_budget"] = budget
    return spec, parameters
