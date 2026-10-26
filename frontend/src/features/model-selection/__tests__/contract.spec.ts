/** 模型选择协议回归：验证固定值、受限范围、坏响应及敏感字段隔离。 */
import { expect, it } from 'vitest'
import { modelOptionsData } from '@tests/support/data/model-selection'
import {
  decodeOptions,
  decodePolicy,
  decodeReasoning,
  decodeSelectionFields,
  validateSelection,
} from '../contract'

it('按连接分组解码并保持独立副本，拒绝重复模型和错误默认', () => {
  const data = modelOptionsData(),
    decoded = decodeOptions(data)
  expect(decoded).toEqual(data)
  expect(decoded.providers[0]!.models[0]!.reasoning_control).not.toBe(
    data.providers[0]!.models[0]!.reasoning_control,
  )
  expect(() =>
    decodeOptions({
      ...data,
      default_selection: { ...data.default_selection, model_configuration_id: 'missing' },
    }),
  ).toThrow('响应格式无效')
  data.providers[0]!.models.push(data.providers[0]!.models[0]!)
  expect(() => decodeOptions(data)).toThrow('响应格式无效')
})
it('具体选择排除 default、混合参数及非整数预算，保留原档位顺序', () => {
  for (const value of [
    { mode: 'default' },
    { mode: 'off', effort: 'high' },
    { mode: 'budget', budget_tokens: 1.5 },
  ])
    expect(() => decodeReasoning(value)).toThrow('模型选择响应格式无效')
  expect(
    decodePolicy({
      mode: 'selectable',
      allowed_modes: ['effort'],
      effort_options: ['max', 'low'],
      budget: null,
    }),
  ).toEqual({
    mode: 'selectable',
    allowed_modes: ['effort'],
    effort_options: ['max', 'low'],
    budget: null,
  })
  for (const value of [
    { mode: 'selectable', allowed_modes: ['off', 'off'], effort_options: [], budget: null },
    { mode: 'selectable', allowed_modes: ['effort'], effort_options: [], budget: null },
  ])
    expect(() => decodePolicy(value)).toThrow('模型选择响应格式无效')
})
it('预算上下界闭区间，固定值变化和动态失效均要求重选', () => {
  const data = modelOptionsData(),
    model = data.providers[0]!.models[0]!,
    selection = data.default_selection!
  for (const budget_tokens of [1024, 8192])
    expect(
      validateSelection({ ...selection, reasoning: { mode: 'budget', budget_tokens } }, model),
    ).toBe('')
  expect(
    validateSelection({ ...selection, reasoning: { mode: 'budget', budget_tokens: 8193 } }, model),
  ).toContain('整数')
  model.reasoning_control = { mode: 'fixed', default: { mode: 'off' } }
  expect(validateSelection(selection, model)).toContain('改变')
  expect(
    decodeSelectionFields({
      model_selection: selection,
      model_selection_version: 3,
      model_selection_issue: 'model_disabled',
    }).model_selection_issue,
  ).toBe('model_disabled')
  expect(() => decodeSelectionFields({ model_selection_version: 0 })).toThrow(
    '模型选择响应格式无效',
  )
  expect(() => decodeSelectionFields({ model_selection_version: null })).toThrow(
    '模型选择响应格式无效',
  )
})
