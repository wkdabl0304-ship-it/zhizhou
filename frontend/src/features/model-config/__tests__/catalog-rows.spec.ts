/** 目录行及首次开启默认值：覆盖旧方案引用保留、失效目录和预算边界。 */
import { expect, it } from 'vitest'
import { modelConfigData } from '@tests/support/data/model-config'
import { catalogRows, initialModel, initialReasoning } from '../catalog-rows'
import { validateModel } from '../validation'

it('目录补齐未保存模型，同模型多份方案及移除目录的旧方案保留原 ID', () => {
  const { catalog, model } = modelConfigData()
  const another = { ...model, id: 'another', name: '另一份推理方案' }
  const retired = { ...model, id: 'retired', catalog_model_id: 'removed:model' }
  const fresh = { ...catalog, catalog_model_id: 'fresh:model' }
  expect(catalogRows([catalog, fresh], [model, another, retired])).toEqual([
    { key: model.id, catalog, model },
    { key: another.id, catalog, model: another },
    { key: fresh.catalog_model_id, catalog: fresh },
    { key: retired.id, model: retired },
  ])
})

it('输出上限变化自动适配初始预算，低于原生下限时关闭且不修改目录', () => {
  const { catalog } = modelConfigData()
  expect(initialReasoning(catalog, 4096)).toEqual({ mode: 'budget', budget_tokens: 4095 })
  expect(initialReasoning(catalog, 1024)).toEqual({ mode: 'off' })
  expect(catalog.reasoning.default).toEqual({ mode: 'budget', budget_tokens: 4096 })
})

it('首次开启使用目录默认推理、合法输出上限和默认开放范围，不变更输入目录', () => {
  const { catalog } = modelConfigData()
  const bounded = { ...catalog, max_output_tokens: 8192 }
  expect(initialModel('connection', bounded)).toMatchObject({
    name: catalog.display_name,
    provider_configuration_id: 'connection',
    enabled: true,
    reasoning: { mode: 'budget', budget_tokens: 4096 },
    max_output_tokens: 8192,
    reasoning_policy: {
      mode: 'selectable',
      allowed_modes: ['off', 'budget'],
      effort_options: [],
      budget: { min: 1024, max: 8191 },
    },
  })
  const largeBudget = {
    ...catalog,
    reasoning: { ...catalog.reasoning, default: { mode: 'budget' as const, budget_tokens: 20000 } },
  }
  const body = initialModel('connection', largeBudget)
  expect(body.max_output_tokens).toBe(20001)
  expect(validateModel(body, largeBudget)).toEqual({})
  expect(catalog.reasoning.default).toEqual({ mode: 'budget', budget_tokens: 4096 })
})
