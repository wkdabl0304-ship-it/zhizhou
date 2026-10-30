/** 统一强度选择回归：关闭是普通可选项，预算与档位不再依赖模式和策略开关。 */
import { expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { modelConfigData } from '@tests/support/data/model-config'
import ReasoningPolicyEditor from '../components/ReasoningPolicyEditor.vue'
import { defaultReasoningPolicy, initialReasoning } from '../catalog-rows'
import { validateModel } from '../validation'
import type { ReasoningPolicy, SelectablePolicy } from '@/features/model-selection/types'
it('默认值须在开放范围，预算上限不得越过输出限制', () => {
  const { model, catalog } = modelConfigData()
  const body = {
    ...model,
    reasoning_policy: {
      mode: 'selectable',
      allowed_modes: ['budget'],
      effort_options: [],
      budget: { min: 1024, max: 8192 },
    } as ReasoningPolicy,
  }
  expect(validateModel(body, catalog)).toEqual({})
  expect(validateModel({ ...body, max_output_tokens: 8192 }, catalog).reasoning_policy).toContain(
    '输出',
  )
  expect(
    validateModel({ ...body, reasoning: { mode: 'off' } }, catalog).reasoning_policy,
  ).toContain('默认')
})

it('不思考与预算直接勾选，移除最后一项保留空草稿并在保存边界报错', async () => {
  const { catalog, model } = modelConfigData()
  const page = mount(ReasoningPolicyEditor, {
    props: {
      model: catalog,
      maxOutput: 16384,
      modelValue: defaultReasoningPolicy(catalog, 16384),
      'onUpdate:modelValue': (value: SelectablePolicy) => {
        void page.setProps({ modelValue: value })
      },
    },
  })
  expect(page.find('[role="combobox"]').exists()).toBe(false)
  await page.get('[name="allow_budget"]').setValue(false)
  expect(page.props('modelValue')).toEqual({
    mode: 'selectable',
    allowed_modes: ['off'],
    effort_options: [],
    budget: null,
  })
  expect(initialReasoning(catalog, 16384, page.props('modelValue'))).toEqual({ mode: 'off' })
  await page.get('[name="allow_off"]').setValue(false)
  expect(
    validateModel({ ...model, reasoning_policy: page.props('modelValue') }, catalog)
      .reasoning_policy,
  ).toBeTruthy()
  await page.get('[name="allow_budget"]').setValue(true)
  await page.get('[name="policy_budget_max"]').setValue('8192')
  expect(page.props('modelValue').budget).toEqual({ min: 1024, max: 8192 })
  expect(initialReasoning(catalog, 16384, page.props('modelValue'))).toEqual({
    mode: 'budget',
    budget_tokens: 4096,
  })
})

it('移除默认档位后自动从允许强度选择初始值，原生不支持关闭时没有关闭选项', async () => {
  const { catalog } = modelConfigData()
  const spec = {
    ...catalog,
    reasoning: {
      ...catalog.reasoning,
      allowed_modes: ['effort' as const],
      effort_options: ['low', 'high'],
      default: { mode: 'effort' as const, effort: 'high' },
      budget: null,
    },
  }
  const page = mount(ReasoningPolicyEditor, {
    props: {
      model: spec,
      maxOutput: 16384,
      modelValue: defaultReasoningPolicy(spec, 16384),
      'onUpdate:modelValue': (value: SelectablePolicy) => {
        void page.setProps({ modelValue: value })
      },
    },
  })
  expect(page.find('[name="allow_off"]').exists()).toBe(false)
  await page.get('[name="allow_effort_high"]').setValue(false)
  expect(page.props('modelValue')).toEqual({
    mode: 'selectable',
    allowed_modes: ['effort'],
    effort_options: ['low'],
    budget: null,
  })
  expect(initialReasoning(spec, 16384, page.props('modelValue'))).toEqual({
    mode: 'effort',
    effort: 'low',
  })
})
