/** 模型目录展示适配：将未保存的目录项与已有方案合并，保留旧方案的身份与引用。 */
import type { CatalogModel, ModelConfiguration, ModelInput } from './types'

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
    reasoning_policy: { mode: 'fixed' },
    enabled: true,
  }
}
