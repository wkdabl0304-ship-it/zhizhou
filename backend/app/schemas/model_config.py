"""模型配置接口的数据约定：区分写入凭据、公开信息及受限的推理参数。"""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

type Provider = Literal["openai", "anthropic", "deepseek", "bailian"]
type ApiFormat = Literal["responses", "chat_completions", "messages"]


class StrictModel(BaseModel):
    """拒绝未声明参数，防止把任意上游请求参数混入业务配置。"""

    model_config = ConfigDict(extra="forbid", from_attributes=True)


class DefaultReasoning(StrictModel):
    """使用模型目录记录的默认推理配置。"""

    mode: Literal["default"] = "default"


class OffReasoning(StrictModel):
    """请求关闭当前模型支持关闭的思考功能。"""

    mode: Literal["off"]


class EffortReasoning(StrictModel):
    """选择模型目录允许的原生推理档位，不接受任意额外参数。"""

    mode: Literal["effort"]
    effort: str = Field(min_length=1, max_length=20)


class BudgetReasoning(StrictModel):
    """为手动思考模型配置 token 预算，具体范围由模型策略校验。"""

    mode: Literal["budget"]
    budget_tokens: int = Field(gt=0, strict=True)


type Reasoning = Annotated[
    DefaultReasoning | OffReasoning | EffortReasoning | BudgetReasoning,
    Field(discriminator="mode"),
]


class EndpointConfig(StrictModel):
    """接收百炼 Base URL 或原有官方端点；旧地域字段仅保留接口及存量数据兼容。"""

    endpoint_id: str | None = Field(default=None, min_length=1, max_length=40)
    workspace_id: str | None = Field(default=None, min_length=1, max_length=100)
    base_url: str | None = Field(default=None, min_length=1, max_length=2048)

    @field_validator("base_url")
    @classmethod
    def normalize_base_url(cls, value: str | None) -> str | None:
        """清除粘贴地址首尾空白与末尾斜杠，不改变请求所用的域名及路径。"""
        if value is None:
            return None
        value = value.strip().rstrip("/")
        if not value:
            raise ValueError("Base URL 不能为空")
        return value

    @model_validator(mode="after")
    def require_endpoint_shape(self) -> Self:
        """确保直接地址与旧端点配置二选一，拒绝冲突字段或没有地址的输入。"""
        if self.base_url is not None:
            if self.endpoint_id is not None or self.workspace_id is not None:
                raise ValueError("Base URL 不能与地域或业务空间同时填写")
        elif self.endpoint_id is None:
            raise ValueError("请提供 Base URL 或官方端点")
        return self


class NamedModel(StrictModel):
    """统一处理用户填写的配置名称，保留非空的可读展示值。"""

    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """去除名称首尾空白并拒绝空白名称。"""
        value = value.strip()
        if not value:
            raise ValueError("名称不能为空")
        return value


class ProviderConfigurationCreate(NamedModel):
    """创建全局供应商配置；密钥只参与写入和运行时解密。"""

    provider: Provider
    api_format: ApiFormat
    endpoint_config: EndpointConfig
    api_key: SecretStr = Field(repr=False)

    @field_validator("api_key")
    @classmethod
    def require_key(cls, value: SecretStr) -> SecretStr:
        """拒绝空密钥，避免客户端从环境变量意外取得其他账号凭据。"""
        if not value.get_secret_value().strip():
            raise ValueError("API Key 不能为空")
        return value


class ProviderConfigurationPatch(StrictModel):
    """按版本修改供应商配置；可选字段省略时保留，显式 null 由服务拒绝。"""

    version: int = Field(gt=0, strict=True)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    api_format: ApiFormat | None = None
    endpoint_config: EndpointConfig | None = None
    api_key: SecretStr | None = Field(default=None, repr=False)


class ProviderConfigurationInfo(NamedModel):
    """供应商配置的公开信息，字段白名单不含密文及内部凭据版本。"""

    id: UUID
    provider: Provider
    api_format: ApiFormat
    endpoint_config: EndpointConfig
    api_key_configured: bool = True
    version: int
    created_at: datetime
    updated_at: datetime


class EndpointOptionInfo(StrictModel):
    """官方端点选项，告诉配置页面哪些地域必须填写业务空间。"""

    endpoint_id: str
    display_name: str
    workspace_id_required: bool


class ProviderInfo(StrictModel):
    """供应商目录的公开契约，不包含底层 SDK 参数或用户凭据。"""

    provider: Provider
    display_name: str
    api_formats: list[ApiFormat]
    default_api_format: ApiFormat
    endpoints: list[EndpointOptionInfo]
    recommended: bool
    provider_configuration_fields: list[str]


class BudgetLimits(StrictModel):
    """模型思考预算的可选范围；与输出上限的关联约束另行声明。"""

    min: int
    max: int


class ReasoningCapabilities(StrictModel):
    """模型推理控件契约，前端可以直接判断开关、档位和预算是否适用。"""

    allowed_modes: list[Literal["default", "off", "effort", "budget"]]
    effort_options: list[str]
    default: Reasoning
    budget: BudgetLimits | None = None
    budget_must_fit_output: bool = False


class ModelCapabilities(StrictModel):
    """当前 Agent 使用的流式文本及工具能力。"""

    streaming: bool
    tool_calling: bool


class CatalogModelInfo(StrictModel):
    """内置模型定义的公开视图，参数处理策略名称不进入协议。"""

    catalog_model_id: str
    provider: Provider
    model_id: str
    display_name: str
    supported_api_formats: list[ApiFormat]
    capabilities: ModelCapabilities
    reasoning: ReasoningCapabilities
    max_output_tokens: int
    available: bool
    verified_at: str
    format_constraints: dict[str, str]


class ModelCreate(NamedModel):
    """把内置模型及其推理设置保存为可复用的模型配置。"""

    provider_configuration_id: UUID
    catalog_model_id: str = Field(min_length=1, max_length=160)
    reasoning: Reasoning = Field(default_factory=DefaultReasoning)
    max_output_tokens: int = Field(default=16384, gt=0, strict=True)


class ModelPatch(StrictModel):
    """按版本修改模型配置；归属固定，更换供应商配置时创建新模型配置。"""

    version: int = Field(gt=0, strict=True)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    catalog_model_id: str | None = Field(default=None, min_length=1, max_length=160)
    reasoning: Reasoning | None = None
    max_output_tokens: int | None = Field(default=None, gt=0, strict=True)


class ModelInfo(ModelCreate):
    """已保存模型配置及当前目录能力；缺失目录项仍能读取和删除。"""

    id: UUID
    version: int
    created_at: datetime
    updated_at: datetime
    catalog: CatalogModelInfo | None = None
    available: bool = True


class DefaultUpdate(StrictModel):
    """以乐观版本切换全局默认，null 表示明确清除默认选择。"""

    version: int = Field(gt=0, strict=True)
    model_configuration_id: UUID | None


class DefaultInfo(StrictModel):
    """全局默认引用及其展示概要，避免复制存储供应商配置和模型参数。"""

    model_configuration_id: UUID | None
    version: int
    updated_at: datetime
    model: ModelInfo | None = None


class ModelTestResult(StrictModel):
    """一次固定文本流测试的结果，不代表工具能力已通过实网验证。"""

    latency_ms: float
    provider_configuration_version: int
    model_version: int
    verified: Literal["streaming_text"] = "streaming_text"
