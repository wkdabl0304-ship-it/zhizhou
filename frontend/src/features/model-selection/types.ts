/** 聊天模型选择契约：只包含允许范围、具体推理值与会话确认状态，不含地址或凭据。 */
export type ConcreteReasoning =
  { mode: 'off' } | { mode: 'effort'; effort: string } | { mode: 'budget'; budget_tokens: number }
export interface ModelSelection {
  model_configuration_id: string
  reasoning: ConcreteReasoning
}
export type SelectablePolicy = {
  mode: 'selectable'
  allowed_modes: ConcreteReasoning['mode'][]
  effort_options: string[]
  budget: { min: number; max: number } | null
}
export type ReasoningPolicy = { mode: 'fixed' } | SelectablePolicy
export type ReasoningControl = ReasoningPolicy & { default: ConcreteReasoning }
export interface SelectableModel {
  model_configuration_id: string
  name: string
  catalog_model_id: string
  display_name: string
  reasoning_control: ReasoningControl
}
export interface ModelOptions {
  default_selection: ModelSelection | null
  providers: {
    provider_configuration_id: string
    name: string
    provider: string
    models: SelectableModel[]
  }[]
}
export type SelectionIssue =
  | 'model_deleted'
  | 'provider_disabled'
  | 'model_disabled'
  | 'model_unavailable'
  | 'reasoning_not_allowed'
export interface SelectionFields {
  model_selection: ModelSelection | null
  model_selection_version: number
  model_selection_issue: SelectionIssue | null
}
