/** 模型配置公开契约：对应后端 model_config schema，写入密钥与公开响应类型分离。 */
import type { ReasoningPolicy } from '@/features/model-selection/types'
export type Provider = 'openai' | 'anthropic' | 'deepseek' | 'bailian'
export type ApiFormat = 'responses' | 'chat_completions' | 'messages'
export type Reasoning =
  | { mode: 'default' }
  | { mode: 'off' }
  | { mode: 'effort'; effort: string }
  | { mode: 'budget'; budget_tokens: number }
export interface Endpoint {
  // 百炼直接保存完整地址；其余供应商沿用官方端点标识。
  base_url?: string | null
  endpoint_id?: string | null
  workspace_id?: string | null
}
export interface ProviderInfo {
  provider: Provider
  display_name: string
  api_formats: ApiFormat[]
  default_api_format: ApiFormat
  endpoints: { endpoint_id: string; display_name: string; workspace_id_required: boolean }[]
  recommended: boolean
  provider_configuration_fields: string[]
}
export interface ProviderConfiguration {
  id: string
  name: string
  provider: Provider
  api_format: ApiFormat
  endpoint_config: Endpoint
  api_key_configured: boolean
  enabled: boolean
  version: number
  created_at: string
  updated_at: string
}
export interface CatalogModel {
  catalog_model_id: string
  provider: Provider
  model_id: string
  display_name: string
  supported_api_formats: ApiFormat[]
  capabilities: { streaming: boolean; tool_calling: boolean }
  reasoning: {
    allowed_modes: Reasoning['mode'][]
    effort_options: string[]
    default: Reasoning
    budget: { min: number; max: number } | null
    budget_must_fit_output: boolean
  }
  max_output_tokens: number
  available: boolean
  verified_at: string
  format_constraints: Record<string, string>
}
export interface ModelInput {
  name: string
  provider_configuration_id: string
  catalog_model_id: string
  reasoning: Reasoning
  max_output_tokens: number
  enabled?: boolean
  reasoning_policy?: ReasoningPolicy
}
export interface ModelConfiguration extends ModelInput {
  enabled: boolean
  reasoning_policy: ReasoningPolicy
  selectable: boolean
  id: string
  version: number
  created_at: string
  updated_at: string
  catalog: CatalogModel | null
  available: boolean
}
export interface DefaultModel {
  model_configuration_id: string | null
  version: number
  updated_at: string
  model: ModelConfiguration | null
}
export interface ProviderInput {
  name: string
  provider: Provider
  api_format: ApiFormat
  endpoint_config: Endpoint
  api_key: string
  enabled?: boolean
}
export type ProviderPatch = Partial<Omit<ProviderInput, 'provider'>> & { version: number }
export type ModelPatch = Partial<Omit<ModelInput, 'provider_configuration_id'>> & {
  version: number
}
export interface TestResult {
  latency_ms: number
  provider_configuration_version: number
  model_version: number
  verified: 'streaming_text'
}
