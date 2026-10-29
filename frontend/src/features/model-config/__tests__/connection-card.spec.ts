/** 连接卡片组件回归：验证选择语义、独立启停、操作入口及保存期间的禁用边界。 */
import { expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { modelConfigData } from '@tests/support/data/model-config'
import ProviderConnectionCard from '../components/ProviderConnectionCard.vue'

it('连接卡片显示摘要、选择状态和直接操作，开关等待服务端更新', async () => {
  const { provider } = modelConfigData()
  const wrapper = mount(ProviderConnectionCard, {
    props: {
      connection: provider,
      selected: true,
      busy: false,
      blocked: false,
    },
  })
  expect(wrapper.text()).toContain(provider.name)
  expect(wrapper.text()).toContain('密钥已配置')
  expect(wrapper.findAll('.ui-tag')).toHaveLength(2)
  expect(wrapper.findAll('.ui-tag').every((tag) => tag.classes().includes('ui-tag--xs'))).toBe(true)
  expect(wrapper.get('.connection-card-select').attributes('aria-pressed')).toBe('true')
  await wrapper.get('.connection-card-select').trigger('click')
  await wrapper.get('[role="switch"]').trigger('click')
  await wrapper.get('[aria-label="编辑供应商"]').trigger('click')
  await wrapper.get('[aria-label="删除供应商"]').trigger('click')
  for (const event of ['select', 'toggle', 'edit', 'delete'])
    expect(wrapper.emitted(event)).toHaveLength(1)
  expect(wrapper.get('[role="switch"]').attributes('aria-checked')).toBe('true')
  await wrapper.setProps({ connection: { ...provider, enabled: false }, selected: false })
  expect(wrapper.get('[role="switch"]').attributes('aria-checked')).toBe('false')
  expect(wrapper.get('.connection-card-select').attributes('aria-pressed')).toBe('false')
  expect(wrapper.text()).toContain('已停用')
})

it('有编辑器时允许受保护的连接切换，保存期间禁止全部操作', async () => {
  const wrapper = mount(ProviderConnectionCard, {
    props: {
      connection: modelConfigData().provider,
      selected: false,
      busy: false,
      blocked: true,
    },
  })
  expect(wrapper.get('.connection-card-select').attributes('disabled')).toBeUndefined()
  for (const button of wrapper.findAll('button:not(.connection-card-select)'))
    expect(button.attributes('disabled')).toBeDefined()
  await wrapper.setProps({ busy: true })
  for (const button of wrapper.findAll('button')) {
    expect(button.attributes('disabled')).toBeDefined()
    await button.trigger('click')
  }
  expect(wrapper.emitted('select')).toBeUndefined()
  expect(wrapper.emitted('toggle')).toBeUndefined()
})
