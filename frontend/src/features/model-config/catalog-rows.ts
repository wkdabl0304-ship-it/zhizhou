/** 模型目录展示适配：将未保存的目录项与已有方案合并，保留旧方案的身份与引用。 */
import type { CatalogModel, ModelConfiguration, ModelInput, Reasoning } from './types'
import type { SelectablePolicy } from '@/features/model-selection/types'

/** 从超管允许范围选择初始思考值，同时适配目录及输出上限。 */
export function initialReasoning(
  catalog: CatalogModel,
  maxOutput: number,
  policy?: SelectablePolicy,
): Reasoning {
  const value = { ...catalog.reasoning.default }
  if (value.mode === 'budget' && catalog.reasoning.budget_must_fit_output) {
    const maximum = Math.min(catalog.reasoning.budget!.max, maxOutput - 1)
    value.budget_tokens = Math.max(
      catalog.reasoning.budget!.min,
      Math.min(value.budget_tokens, maximum),
    )
    if (
      maximum < catalog.reasoning.budget!.min &&
      (!policy || policy.allowed_modes.includes('off'))
    )
      return { mode: 'off' }
  }
  if (policy) {
    if (value.mode === 'effort' && policy.effort_options.includes(value.effort)) return value
    if (value.mode === 'budget' && policy.budget)
      return {
        mode: 'budget',
        budget_tokens: Math.max(
          policy.budget.min,
          Math.min(value.budget_tokens, policy.budget.max),
        ),
      }
    if (value.mode === 'off' && policy.allowed_modes.includes('off')) return value
    if (policy.effort_options.length) return { mode: 'effort', effort: policy.effort_options[0]! }
    if (policy.budget) return { mode: 'budget', budget_tokens: policy.budget.min }
    return { mode: 'off' }
  }
  return value
}

/** 默认勾选模型支持的全部强度，预算上限自动适配输出空间。 */
export function defaultReasoningPolicy(catalog: CatalogModel, maxOutput: number): SelectablePolicy {
  const capability = catalog.reasoning
  const budget = capability.budget ? { ...capability.budget } : null
  if (budget && capability.budget_must_fit_output)
    budget.max = Math.min(budget.max, Math.max(budget.min, maxOutput - 1))
  return {
    mode: 'selectable',
    allowed_modes: capability.allowed_modes.filter((mode) => mode !== 'default'),
    effort_options: [...capability.effort_options],
    budget,
  }
}

export interface CatalogRow {
  key: string
  catalog?: CatalogModel
  model?: ModelConfiguration
}

/** 按目录排列模型行；同模型的多份旧方案分别展示，目录移除的方案留在末尾。 */
export function catalogRows(catalog: CatalogModel[], models: ModelConfiguration[]): CatalogRow[] {
  const rows: CatalogRow[] = []
  const seen = new Set<string>()
  for (const entry of catalog) {
    seen.add(entry.catalog_model_id)
    const saved = models.filter((model) => model.catalog_model_id === entry.catalog_model_id)
    if (saved.length) {
      for (const model of saved) rows.push({ key: model.id, catalog: entry, model })
    } else rows.push({ key: entry.catalog_model_id, catalog: entry })
  }
  for (const model of models) {
    if (!seen.has(model.catalog_model_id)) rows.push({ key: model.id, model })
  }
  return rows
}

/** 为首次开启构造合法默认配置，不改变全局默认，也不调用上游模型。 */
export function initialModel(providerId: string, catalog: CatalogModel): ModelInput {
  const reasoning = { ...catalog.reasoning.default }
  const minimumOutput =
    catalog.reasoning.budget_must_fit_output && reasoning.mode === 'budget'
      ? reasoning.budget_tokens + 1
      : 1
  return {
    provider_configuration_id: providerId,
    catalog_model_id: catalog.catalog_model_id,
    name: catalog.display_name,
    reasoning,
    max_output_tokens: Math.min(catalog.max_output_tokens, Math.max(16384, minimumOutput)),
    reasoning_policy: defaultReasoningPolicy(
      catalog,
      Math.min(catalog.max_output_tokens, Math.max(16384, minimumOutput)),
    ),
    enabled: true,
  }
}
