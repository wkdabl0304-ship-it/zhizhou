"""模型策略回归：验证公开配置能力与实际传参一致，并拒绝非法组合。"""

import pytest

from app.llm.models.catalog import CATALOG, list_models
from app.llm.models.policy import resolve_parameters
from app.schemas.model_config import BudgetReasoning, DefaultReasoning, EffortReasoning, OffReasoning


@pytest.mark.parametrize("spec", CATALOG.values(), ids=list(CATALOG))
def test_every_advertised_model_and_format_has_valid_default(spec):
    """所有公开模型及其格式都能生成默认参数，避免目录出现无法执行的选项。"""
    for api_format in spec.formats:
        actual, params = resolve_parameters(spec.provider, api_format, spec.catalog_model_id, DefaultReasoning(), 16384)
        assert actual is spec and params["model"] == spec.model_id
        assert spec.describe(api_format)["capabilities"]["tool_calling"]


@pytest.mark.parametrize("provider,model_id,api_format,reasoning,expected", [
    ("deepseek", "deepseek-flash", "chat_completions", EffortReasoning(mode="effort", effort="max"), {"thinking": {"type": "enabled"}}),
    ("deepseek", "deepseek-flash", "chat_completions", OffReasoning(mode="off"), {"thinking": {"type": "disabled"}}),
])
def test_deepseek_thinking_toggle_and_effort(provider, model_id, api_format, reasoning, expected):
    """DeepSeek 开关与强度按原生字段组合，关闭时不会残留强度参数。"""
    _, params = resolve_parameters(provider, api_format, f"{provider}:{model_id}", reasoning, 16384)
    assert params["extra_body"] == expected
    assert params.get("reasoning_effort") == ("max" if reasoning.mode == "effort" else None)


def test_claude_budget_and_qwen_native_settings():
    """预算型 Claude 和 Qwen 使用各自的原生参数，不编造 effort 档位。"""
    _, claude = resolve_parameters("anthropic", "messages", "anthropic:claude-haiku-4-5-20251001", BudgetReasoning(mode="budget", budget_tokens=4096), 16384)
    assert claude["thinking"] == {"type": "enabled", "budget_tokens": 4096}
    assert "output_config" not in claude
    _, qwen = resolve_parameters("bailian", "chat_completions", "bailian:qwen3.7-plus", BudgetReasoning(mode="budget", budget_tokens=4096), 16384)
    assert qwen["enable_thinking"] and qwen["thinking_budget"] == 4096
    _, qwen = resolve_parameters("bailian", "chat_completions", "bailian:qwen3.8-max", BudgetReasoning(mode="budget", budget_tokens=16384), 16384)
    assert qwen["thinking_budget"] == 16384 and "reasoning_effort" not in qwen


def test_openai_formats_and_tool_restrictions():
    """GPT-6 的 Chat 工具限制在本地校验；Responses 明确关闭上游状态存储。"""
    _, params = resolve_parameters("openai", "responses", "openai:gpt-6.1-sol", DefaultReasoning(), 16384)
    assert params["reasoning"] == {"effort": "medium"} and params["store"] is False
    _, params = resolve_parameters("openai", "chat_completions", "openai:gpt-6-sol", DefaultReasoning(), 16384)
    assert params["reasoning_effort"] == "none" and params["use_responses_api"] is False
    assert list_models("openai", "chat_completions")
    assert all(item["model_id"] != "gpt-6-astra" for item in list_models("openai", "chat_completions"))


@pytest.mark.parametrize("provider,api_format,model,reasoning,limit", [
    ("openai", "chat_completions", "openai:gpt-6-astra", DefaultReasoning(), 16384),
    ("openai", "chat_completions", "openai:gpt-6-sol", EffortReasoning(mode="effort", effort="high"), 16384),
    ("deepseek", "chat_completions", "deepseek:deepseek-flash", EffortReasoning(mode="effort", effort="medium"), 16384),
    ("anthropic", "messages", "anthropic:claude-opus-5-5", OffReasoning(mode="off"), 16384),
    ("anthropic", "messages", "anthropic:claude-haiku-4-5-20251001", BudgetReasoning(mode="budget", budget_tokens=16384), 16384),
    ("anthropic", "messages", "anthropic:claude-haiku-4-5-20251001", BudgetReasoning(mode="budget", budget_tokens=512), 16384),
    ("bailian", "chat_completions", "bailian:qwen3.7-plus", EffortReasoning(mode="effort", effort="high"), 16384),
    ("deepseek", "chat_completions", "openai:gpt-6-astra", DefaultReasoning(), 16384),
    ("deepseek", "chat_completions", "deepseek:unknown", DefaultReasoning(), 16384),
    ("deepseek", "chat_completions", "deepseek:deepseek-flash", DefaultReasoning(), 999999),
])
def test_rejects_invalid_combinations(provider, api_format, model, reasoning, limit):
    """错误档位、预算、格式、供应商归属和未知模型均在请求上游前拒绝。"""
    with pytest.raises(ValueError):
        resolve_parameters(provider, api_format, model, reasoning, limit)
