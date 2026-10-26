/** 管理推理策略回归：范围必须来自目录，固定与自选切换不残留不适用字段。 */
import { expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { modelConfigData } from '@tests/support/data/model-config'
import ReasoningPolicyEditor from '../components/ReasoningPolicyEditor.vue'
import { validateModel } from '../validation'
import type { ReasoningPolicy } from '@/features/model-selection/types'
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
it('切换策略生成合法预算范围，移除预算方式时不残留预算字段', async () => {
  const { catalog } = modelConfigData()
  const page = mount(ReasoningPolicyEditor, {
    props: {
      model: catalog,
      reasoning: { mode: 'budget', budget_tokens: 4096 },
      maxOutput: 16384,
      modelValue: { mode: 'fixed' },
      'onUpdate:modelValue': (value: ReasoningPolicy) => {
        void page.setProps({ modelValue: value })
      },
    },
  })
  await page.get('select').setValue('selectable')
  const policy = page.props('modelValue')
  expect(policy).toEqual({
    mode: 'selectable',
    allowed_modes: ['budget'],
    effort_options: [],
    budget: { min: 1024, max: 16383 },
  })
  await page.get('[name="allow_off"]').setValue(true)
  await page.get('[name="allow_budget"]').setValue(false)
  expect(page.props('modelValue')).toEqual({
    mode: 'selectable',
    allowed_modes: ['off'],
    effort_options: [],
    budget: null,
  })
  await page.get('select').setValue('fixed')
  expect(page.props('modelValue')).toEqual({ mode: 'fixed' })
})
