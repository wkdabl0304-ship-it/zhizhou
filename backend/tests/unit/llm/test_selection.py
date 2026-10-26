"""受限推理单元测试：验证范围、原生能力及固定值约束，不访问供应商或数据库。"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.llm.models.selection import concrete_reasoning, require_allowed, validate_policy
from app.schemas.model_config import ModelCreate, OffReasoning, EffortReasoning
from app.schemas.model_selection import ModelSelection


def configuration(**changes):
    """构造独立的 DeepSeek 方案，便于各用例只声明需要验证的限制。"""
    return ModelCreate.model_validate({
        "name": "测试方案", "provider_configuration_id": uuid4(),
        "catalog_model_id": "deepseek:deepseek-flash", **changes,
    })


def test_fixed_default_is_concrete_and_cannot_be_overridden():
    """目录默认解析后按固定值比较，关闭或其他合法原生档位也不能越权覆盖。"""
    body = configuration()
    validate_policy("deepseek", "chat_completions", body)
    default = concrete_reasoning(body, "chat_completions")
    assert default.model_dump() == {"mode": "effort", "effort": "high"}
    require_allowed(body, default, default)
    for selected in (OffReasoning(mode="off"), EffortReasoning(mode="effort", effort="low")):
        with pytest.raises(ValueError):
            require_allowed(body, default, selected)


def test_selectable_subset_and_default_must_both_be_valid():
    """只开放白名单中的方式和档位，默认值也不能越过限制。"""
    policy = {"mode": "selectable", "allowed_modes": ["effort"], "effort_options": ["low", "high"]}
    body = configuration(reasoning_policy=policy)
    validate_policy("deepseek", "chat_completions", body)
    default = concrete_reasoning(body, "chat_completions")
    require_allowed(body, default, EffortReasoning(mode="effort", effort="low"))
    for selected in (OffReasoning(mode="off"), EffortReasoning(mode="effort", effort="max")):
        with pytest.raises(ValueError):
            require_allowed(body, default, selected)
    for options in (["medium"], ["low"]):
        with pytest.raises(ValueError):
            validate_policy("deepseek", "chat_completions", configuration(reasoning_policy={**policy, "effort_options": options}))


@pytest.mark.parametrize("policy", [
    {"allowed_modes": []},
    {"allowed_modes": ["off", "off"]},
    {"allowed_modes": ["default"]},
    {"allowed_modes": ["effort"]},
    {"allowed_modes": ["off"], "effort_options": ["high"]},
    {"allowed_modes": ["effort"], "effort_options": ["high", "high"]},
    {"allowed_modes": ["budget"]},
    {"allowed_modes": ["off"], "budget": {"min": 1, "max": 2}},
    {"allowed_modes": ["budget"], "budget": {"min": 2, "max": 1}},
    {"allowed_modes": ["budget"], "budget": {"min": True, "max": 4}},
])
def test_rejects_malformed_policy(policy):
    """重复、缺失、未知方式、反向区间和布尔预算均在输入边界拒绝。"""
    with pytest.raises(ValidationError):
        configuration(reasoning_policy={"mode": "selectable", **policy})


@pytest.mark.parametrize("maximum,valid", [(8192, True), (16383, True), (16384, False), (64000, False)])
def test_claude_budget_range_must_fit_output(maximum, valid):
    """预算闭区间两端均须满足 Claude 原生下限及小于输出上限的关系。"""
    body = configuration(catalog_model_id="anthropic:claude-haiku-4-5-20251001",
                         reasoning={"mode": "budget", "budget_tokens": 4096},
                         reasoning_policy={"mode": "selectable", "allowed_modes": ["off", "budget"],
                                           "budget": {"min": 1024, "max": maximum}})
    if valid:
        validate_policy("anthropic", "messages", body)
    else:
        with pytest.raises(ValueError):
            validate_policy("anthropic", "messages", body)


def test_protocol_constraints_cannot_be_bypassed_by_policy():
    """GPT Chat 的工具限制及不支持关闭的模型都不能通过范围配置扩大能力。"""
    body = configuration(catalog_model_id="openai:gpt-6-sol", reasoning={"mode": "off"},
                         reasoning_policy={"mode": "selectable", "allowed_modes": ["off", "effort"], "effort_options": ["high"]})
    with pytest.raises(ValueError):
        validate_policy("openai", "chat_completions", body)
    body = configuration(catalog_model_id="anthropic:claude-opus-5-5",
                         reasoning_policy={"mode": "selectable", "allowed_modes": ["off", "effort"], "effort_options": ["medium"]})
    with pytest.raises(ValueError):
        validate_policy("anthropic", "messages", body)


def test_chat_selection_accepts_only_concrete_reasoning_and_known_fields():
    """聊天不能借 default、地址、密钥或输出参数绕过方案限制。"""
    for reasoning in ({"mode": "default"}, {"mode": "off", "api_key": "injected"}):
        with pytest.raises(ValidationError):
            ModelSelection(model_configuration_id=uuid4(), reasoning=reasoning)
    with pytest.raises(ValidationError):
        ModelSelection(model_configuration_id=uuid4(), reasoning={"mode": "off"}, max_output_tokens=999999)
