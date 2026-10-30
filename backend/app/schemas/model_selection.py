"""会话模型选择契约：只公开方案引用和具体推理值，不接收供应商凭据及 SDK 参数。"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from app.schemas.model_config import (
    BudgetReasoning, EffortReasoning, FixedReasoningPolicy, OffReasoning,
    Provider, SelectableReasoningPolicy, StrictModel,
)

type ConcreteReasoning = Annotated[
    OffReasoning | EffortReasoning | BudgetReasoning, Field(discriminator="mode")
]
type SelectionIssue = Literal[
    "model_deleted", "provider_disabled", "model_disabled", "model_unavailable", "reasoning_not_allowed"
]


class ModelSelection(StrictModel):
    """保存用户明确选择的方案和具体推理值，禁止 default 绕过限制。"""

    model_configuration_id: UUID
    reasoning: ConcreteReasoning


class ModelSelectionUpdate(StrictModel):
    """按版本替换选择；显式 null 请求自动恢复失效选择，合法选择保持不变。"""

    model_selection_version: int = Field(gt=0, strict=True)
    model_selection: ModelSelection | None


class ModelIdentity(StrictModel):
    """公开实际使用的模型身份，仅包含方案引用、目录标识及展示名称。"""

    model_configuration_id: UUID
    catalog_model_id: str
    display_name: str


class FixedReasoningControl(FixedReasoningPolicy):
    """向聊天界面展示当前固定的具体推理值。"""

    default: ConcreteReasoning


class SelectableReasoningControl(SelectableReasoningPolicy):
    """向聊天界面返回经过模型能力验证的范围和具体默认值。"""

    default: ConcreteReasoning


class SelectableModel(StrictModel):
    """聊天可选方案的展示字段，不包含输出上限等可覆盖运行参数。"""

    model_configuration_id: UUID
    name: str
    catalog_model_id: str
    display_name: str
    reasoning_control: Annotated[
        FixedReasoningControl | SelectableReasoningControl, Field(discriminator="mode")
    ]


class SelectableProvider(StrictModel):
    """按供应商连接分组的有效模型，不公开端点或凭据元数据。"""

    provider_configuration_id: UUID
    name: str
    provider: Provider
    models: list[SelectableModel]


class ModelOptions(StrictModel):
    """一次配置查询快照得到的可选模型和有效全局默认。"""

    default_selection: ModelSelection | None
    providers: list[SelectableProvider]
