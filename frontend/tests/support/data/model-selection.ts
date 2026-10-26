/** 聊天选择测试数据：独立工厂提供连接分组与具体推理范围，不携带密钥或地址。 */
import type { ModelOptions } from '@/features/model-selection/types'
import { modelConfigData } from './model-config'
/** 建立与配置工厂一致、支持关闭思考及手动预算的允许范围。 */
export function modelOptionsData(): ModelOptions {
  const data = modelConfigData()
  return {
    default_selection: {
      model_configuration_id: data.model.id,
      reasoning: { mode: 'budget', budget_tokens: 4096 },
    },
    providers: [
      {
        provider_configuration_id: data.provider.id,
        name: data.provider.name,
        provider: data.provider.provider,
        models: [
          {
            model_configuration_id: data.model.id,
            name: data.model.name,
            catalog_model_id: data.catalog.catalog_model_id,
            display_name: data.catalog.display_name,
            reasoning_control: {
              mode: 'selectable',
              default: { mode: 'budget', budget_tokens: 4096 },
              allowed_modes: ['off', 'budget'],
              effort_options: [],
              budget: { min: 1024, max: 8192 },
            },
          },
        ],
      },
    ],
  }
}
