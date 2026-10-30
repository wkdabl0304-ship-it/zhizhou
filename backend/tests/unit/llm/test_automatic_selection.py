"""自动聊天能力回归：旧固定方案默认开放原生范围，超管自选范围保持有效。"""

from uuid import uuid4

import pytest

from app.llm.models.selection import automatic_configuration, concrete_reasoning, require_allowed, validate_policy
from app.schemas.model_config import ModelCreate, OffReasoning, EffortReasoning


def test_legacy_fixed_policy_opens_native_chat_choices():
    """存量固定设置默认开放关闭及全部合法档位，自动派生不修改原输入。"""
    policy = {"mode": "fixed"}
    body = ModelCreate(name="旧方案", provider_configuration_id=uuid4(),
                       catalog_model_id="deepseek:deepseek-flash", reasoning_policy=policy)
    original = body.model_dump()
    effective = automatic_configuration(body, "chat_completions")
    validate_policy("deepseek", "chat_completions", effective)
    default = concrete_reasoning(effective, "chat_completions")
    require_allowed(effective, default, OffReasoning(mode="off"))
    for effort in ("low", "high", "max"):
        require_allowed(effective, default, EffortReasoning(mode="effort", effort=effort))
    assert body.model_dump() == original


@pytest.mark.parametrize("output,maximum", [(16384, 16383), (2048, 2047)])
def test_automatic_budget_fits_output(output, maximum):
    """自动范围严格小于输出上限，保持目录原生下限。"""
    body = ModelCreate(name="预算", provider_configuration_id=uuid4(),
                       catalog_model_id="anthropic:claude-haiku-4-5-20251001", max_output_tokens=output,
                       reasoning={"mode": "off"})
    effective = automatic_configuration(body, "messages")
    validate_policy("anthropic", "messages", effective)
    assert effective.reasoning_policy.budget.model_dump() == {"min": 1024, "max": maximum}


def test_protocol_constraints_and_insufficient_budget_are_preserved():
    """原生不能关闭的模型不开放关闭，协议限制与不足预算不能被自动策略扩大。"""
    for catalog_id, api_format, output, modes in (
        ("anthropic:claude-opus-5-5", "messages", 16384, ["effort"]),
        ("openai:gpt-6-sol", "chat_completions", 16384, ["off"]),
        ("anthropic:claude-haiku-4-5-20251001", "messages", 1024, ["off"]),
    ):
        body = ModelCreate(name="原生边界", provider_configuration_id=uuid4(),
                           catalog_model_id=catalog_id, max_output_tokens=output)
        assert automatic_configuration(body, api_format).reasoning_policy.allowed_modes == modes


def test_admin_strength_range_still_rejects_off_and_other_efforts():
    """超管只允许低档时，不思考与其他原生强度均不能绕过白名单。"""
    body = ModelCreate(name="只允许低档", provider_configuration_id=uuid4(),
                       catalog_model_id="deepseek:deepseek-flash", reasoning={"mode": "effort", "effort": "low"},
                       reasoning_policy={"mode": "selectable", "allowed_modes": ["effort"], "effort_options": ["low"]})
    effective = automatic_configuration(body, "chat_completions")
    validate_policy("deepseek", "chat_completions", effective)
    default = concrete_reasoning(effective, "chat_completions")
    for selected in (OffReasoning(mode="off"), EffortReasoning(mode="effort", effort="high")):
        with pytest.raises(ValueError):
            require_allowed(effective, default, selected)
