/** 模型配置契约工厂：每次返回独立对象，目录能力和版本可由场景有意修改。 */
import type {
  CatalogModel,
  DefaultModel,
  ModelConfiguration,
  ProviderConfiguration,
  ProviderInfo,
} from '@/features/model-config/types'

/** 建立一份具有手动预算能力的独立模型配置测试数据。 */
export function modelConfigData() {
  const brand: ProviderInfo = {
    provider: 'anthropic',
    display_name: 'Anthropic',
    api_formats: ['messages'],
    default_api_format: 'messages',
    endpoints: [
      { endpoint_id: 'official', display_name: '官方服务', workspace_id_required: false },
    ],
    recommended: false,
    provider_configuration_fields: ['name', 'api_format', 'endpoint_config', 'api_key'],
  }
  const provider: ProviderConfiguration = {
    id: 'provider-one',
    name: 'Claude 官方',
    provider: 'anthropic',
    api_format: 'messages',
    endpoint_config: { endpoint_id: 'official' },
    api_key_configured: true,
    version: 1,
    created_at: '2026-10-24T00:00:00Z',
    updated_at: '2026-10-24T00:00:00Z',
  }
  const catalog: CatalogModel = {
    catalog_model_id: 'anthropic:haiku',
    provider: 'anthropic',
    model_id: 'haiku',
    display_name: 'Claude Haiku',
    supported_api_formats: ['messages'],
    capabilities: { streaming: true, tool_calling: true },
    reasoning: {
      allowed_modes: ['default', 'off', 'budget'],
      effort_options: [],
      default: { mode: 'budget', budget_tokens: 4096 },
      budget: { min: 1024, max: 63999 },
      budget_must_fit_output: true,
    },
    max_output_tokens: 64000,
    available: true,
    verified_at: '2026-10-23',
    format_constraints: {},
  }
  const model: ModelConfiguration = {
    id: 'model-one',
    name: '长文分析',
    provider_configuration_id: provider.id,
    catalog_model_id: catalog.catalog_model_id,
    reasoning: { mode: 'default' },
    max_output_tokens: 16384,
    version: 1,
    created_at: provider.created_at,
    updated_at: provider.updated_at,
    catalog,
    available: true,
  }
  const selected: DefaultModel = {
    model_configuration_id: model.id,
    version: 1,
    updated_at: provider.updated_at,
    model,
  }
  return { brand, provider, catalog, model, selected }
}

/** 建立直接填写 Base URL 的百炼配置，旧地域目录仅保留为兼容元数据。 */
export function bailianConfigData() {
  const data = modelConfigData()
  const brand: ProviderInfo = {
    ...data.brand,
    provider: 'bailian',
    display_name: '阿里云百炼',
    api_formats: ['chat_completions'],
    default_api_format: 'chat_completions',
    endpoints: [{ endpoint_id: 'cn-beijing', display_name: '北京', workspace_id_required: false }],
  }
  const provider: ProviderConfiguration = {
    ...data.provider,
    name: '百炼工作空间',
    provider: 'bailian',
    api_format: 'chat_completions',
    endpoint_config: {
      base_url: 'https://ws-demo.cn-beijing.maas.aliyuncs.com/compatible-mode/v1',
    },
  }
  return { brand, provider }
}
