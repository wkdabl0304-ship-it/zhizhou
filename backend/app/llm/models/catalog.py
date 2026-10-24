"""官方主力模型目录：2026-10-23 核对，明确列出 ID、能力与模型处理策略。

资料：OpenAI /api/docs/guides/reasoning、Claude /docs/en/build-with-claude/thinking、
DeepSeek /guides/thinking_mode、百炼 /zh/model-studio/qwen-api-via-openai-chat-completions。
目录是后端支持范围，不声明当前账号已获访问权限；不按未知模型名前缀猜测能力。
"""

from dataclasses import dataclass

from app.schemas.model_config import ApiFormat, Provider


@dataclass(frozen=True)
class ModelSpec:
    """声明单个官方模型的参数边界，由目录 API 和参数处理层共同使用。"""

    provider: Provider
    model_id: str
    display_name: str
    policy: str
    formats: tuple[ApiFormat, ...]
    efforts: tuple[str, ...] = ()
    default_effort: str | None = None
    can_disable: bool = True
    max_output_tokens: int = 128000
    budget_max: int | None = None
    default_budget: int | None = None
    available: bool = True

    @property
    def catalog_model_id(self) -> str:
        """返回包含供应商命名空间的稳定目录标识。"""
        return f"{self.provider}:{self.model_id}"

    def describe(self, api_format: ApiFormat | None = None) -> dict:
        """为配置页面提供适用于所选格式的模型能力和推理控件信息。"""
        modes = ["default"]
        if self.can_disable:
            modes.append("off")
        efforts = list(self.efforts)
        default = {"mode": "default"}
        # GPT-6 Sol/Luna 在 Chat 格式下仅关闭推理时支持本项目需要的工具调用。
        chat_off_only = self.policy == "openai6" and api_format == "chat_completions"
        if efforts and not chat_off_only:
            modes.append("effort")
            default = {"mode": "effort", "effort": self.default_effort}
        if self.budget_max:
            modes.append("budget")
            if not self.efforts:
                default = {"mode": "budget", "budget_tokens": self.default_budget}
        if chat_off_only:
            modes = ["off"]
            efforts = []
            default = {"mode": "off"}
        reasoning = {"allowed_modes": modes, "effort_options": efforts, "default": default}
        if self.budget_max:
            reasoning["budget"] = {"min": 1024 if self.provider == "anthropic" else 1, "max": self.budget_max}
            reasoning["budget_must_fit_output"] = self.provider == "anthropic"
        return {
            "catalog_model_id": self.catalog_model_id, "provider": self.provider,
            "model_id": self.model_id, "display_name": self.display_name,
            "supported_api_formats": list(self.formats),
            "capabilities": {"streaming": True, "tool_calling": True},
            "reasoning": reasoning, "max_output_tokens": self.max_output_tokens,
            "available": self.available, "verified_at": "2026-10-23",
            "format_constraints": {"chat_completions": "off_only_with_tools"} if self.policy == "openai6" else {},
        }


_OPENAI_EFFORTS = ("low", "medium", "high", "xhigh", "max")
_CLAUDE_EFFORTS = ("low", "medium", "high", "xhigh", "max")

# 同一模型系列共享策略；登记时仍逐项确认其关闭思考及接口格式限制。
_SPECS = (
    ModelSpec("openai", "gpt-6-astra", "GPT-6 Astra", "openai", ("responses",), _OPENAI_EFFORTS, "medium", False),
    ModelSpec("openai", "gpt-6.1-sol", "GPT-6.1 Sol", "openai", ("responses",), _OPENAI_EFFORTS, "medium", False),
    ModelSpec("openai", "gpt-6-sol", "GPT-6 Sol", "openai6", ("responses", "chat_completions"), _OPENAI_EFFORTS, "medium"),
    ModelSpec("openai", "gpt-6-luna", "GPT-6 Luna", "openai6", ("responses", "chat_completions"), _OPENAI_EFFORTS, "medium"),
    *(ModelSpec("openai", f"gpt-5.6-{tier}", f"GPT-5.6 {tier.title()}", "openai", ("responses", "chat_completions"), _OPENAI_EFFORTS, "medium") for tier in ("sol", "terra", "luna")),
    ModelSpec("anthropic", "claude-opus-5-5", "Claude Opus 5.5", "claude", ("messages",), _CLAUDE_EFFORTS, "medium", False),
    ModelSpec("anthropic", "claude-opus-5", "Claude Opus 5", "claude", ("messages",), _CLAUDE_EFFORTS, "high"),
    ModelSpec("anthropic", "claude-sonnet-5-5", "Claude Sonnet 5.5", "claude", ("messages",), _CLAUDE_EFFORTS, "high", False),
    ModelSpec("anthropic", "claude-sonnet-5", "Claude Sonnet 5", "claude", ("messages",), _CLAUDE_EFFORTS, "high"),
    ModelSpec("anthropic", "claude-haiku-5-5", "Claude Haiku 5.5", "claude", ("messages",), _CLAUDE_EFFORTS, "medium"),
    ModelSpec("anthropic", "claude-haiku-4-5-20251001", "Claude Haiku 4.5", "claude_budget", ("messages",), max_output_tokens=64000, budget_max=63999, default_budget=4096),
    ModelSpec("deepseek", "deepseek-flash", "DeepSeek Flash", "deepseek", ("chat_completions",), ("low", "high", "max"), "high", max_output_tokens=393216),
    ModelSpec("deepseek", "deepseek-v4-pro", "DeepSeek V4 Pro", "deepseek", ("chat_completions",), ("low", "high", "max"), "high", max_output_tokens=393216),
    *(ModelSpec("bailian", model_id, model_id, "qwen_effort", ("chat_completions",), ("low", "medium", "xhigh"), "xhigh", max_output_tokens=65536, budget_max=262144, default_budget=131072) for model_id in ("qwen3.8-max", "qwen3.8-flash")),
    *(ModelSpec("bailian", model_id, model_id, "qwen_budget", ("chat_completions",), max_output_tokens=65536, budget_max=32768, default_budget=4096) for model_id in ("qwen3.7-max", "qwen3.7-plus", "qwen3.6-plus", "qwen3.7-flash")),
)
CATALOG = {spec.catalog_model_id: spec for spec in _SPECS}


def list_models(provider: Provider | None = None, api_format: ApiFormat | None = None) -> list[dict]:
    """返回已适配目录，按供应商和接口格式筛选并计算对应参数选项。"""
    return [spec.describe(api_format) for spec in CATALOG.values()
            if (provider is None or spec.provider == provider)
            and (api_format is None or api_format in spec.formats)]
