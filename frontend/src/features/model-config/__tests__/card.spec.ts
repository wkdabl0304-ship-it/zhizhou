/** 模型目录行回归：验证受控开关、不可用模型管理及测试结论的版本边界。 */
import { expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { modelConfigData } from '@tests/support/data/model-config'
import CatalogModelRow from '../components/CatalogModelRow.vue'
import UiSwitch from '@/shared/components/ui/UiSwitch.vue'

it('开关请求不预改受控值，等待或禁用时不能重复请求', async () => {
  const wrapper = mount(UiSwitch, { props: { modelValue: false, label: '启用模型' } })
  await wrapper.get('button').trigger('click')
  expect(wrapper.emitted('update:modelValue')).toEqual([[true]])
  expect(wrapper.get('button').attributes('aria-checked')).toBe('false')
  await wrapper.setProps({ modelValue: true })
  expect(wrapper.get('button').attributes('aria-checked')).toBe('true')
  await wrapper.setProps({ busy: true })
  expect(wrapper.get('button').attributes('disabled')).toBeDefined()
  await wrapper.get('button').trigger('click')
  expect(wrapper.emitted('update:modelValue')).toHaveLength(1)
})

it('配置版本变化使旧测试失效，不可用模型仍能停用和删除', async () => {
  const { model } = modelConfigData()
  const wrapper = mount(CatalogModelRow, {
    props: {
      row: { key: model.id, model },
      connected: true,
      providerEnabled: true,
      current: true,
      busy: false,
      editing: false,
      providerVersion: 2,
      test: {
        running: false,
        result: {
          latency_ms: 50,
          model_version: 1,
          provider_configuration_version: 1,
          verified: 'streaming_text',
        },
      },
    },
  })
  expect(wrapper.text()).toContain('配置已修改，请重新测试')
  expect(wrapper.get('h3 .ui-tag').classes()).toContain('ui-tag--xs')
  expect(wrapper.get('.catalog-model-identity > .ui-tag').classes()).toContain('ui-tag--sm')
  expect(wrapper.text()).not.toContain('文本流通过')
  await wrapper.setProps({ row: { key: model.id, model: { ...model, available: false } } })
  expect(
    wrapper
      .findAll('button')
      .find((button) => button.text() === '测试')!
      .attributes('disabled'),
  ).toBeDefined()
  expect(wrapper.get('[role="switch"]').attributes('disabled')).toBeUndefined()
  await wrapper.get('[role="switch"]').trigger('click')
  await wrapper
    .findAll('button')
    .find((button) => button.text() === '高级设置')!
    .trigger('click')
  await wrapper
    .findAll('button')
    .find((button) => button.text() === '删除')!
    .trigger('click')
  expect(wrapper.emitted('toggle')).toHaveLength(1)
  expect(wrapper.emitted('edit')).toHaveLength(1)
  expect(wrapper.emitted('delete')).toHaveLength(1)
  await wrapper.setProps({
    row: { key: model.id, model: { ...model, available: false, enabled: false } },
  })
  expect(wrapper.get('[role="switch"]').attributes('disabled')).toBeDefined()
})

it('已保存模型直接显示参数和四个操作，默认状态切换后提供清除入口', async () => {
  const { model } = modelConfigData()
  const wrapper = mount(CatalogModelRow, {
    props: {
      row: { key: model.id, model },
      connected: true,
      providerEnabled: true,
      providerVersion: 1,
      current: false,
      busy: false,
      editing: false,
    },
  })
  expect(wrapper.get('.catalog-model-footer').text()).toContain('模型默认 · 输出上限 16,384')
  expect(wrapper.find('summary').exists()).toBe(false)
  const actions = wrapper.get('[role="group"]')
  expect(actions.findAll('button').map((button) => button.text())).toEqual([
    '设为默认',
    '高级设置',
    '测试',
    '删除',
  ])
  for (const button of actions.findAll('button')) await button.trigger('click')
  for (const event of ['select', 'edit', 'test', 'delete'])
    expect(wrapper.emitted(event)).toHaveLength(1)
  await wrapper.setProps({ current: true })
  expect(actions.findAll('button')[0]?.text()).toBe('清除默认')
  await actions.findAll('button')[0]!.trigger('click')
  expect(wrapper.emitted('clear')).toHaveLength(1)
  await wrapper.setProps({ busy: true })
  for (const button of actions.findAll('button'))
    expect(button.attributes('disabled')).toBeDefined()
})

it('未保存目录仅提供启用入口，不显示需要已有配置的操作', () => {
  const { catalog } = modelConfigData()
  const wrapper = mount(CatalogModelRow, {
    props: {
      row: { key: catalog.catalog_model_id, catalog },
      connected: false,
      providerEnabled: false,
      providerVersion: 0,
      current: false,
      busy: false,
      editing: false,
    },
  })
  expect(wrapper.find('[role="group"]').exists()).toBe(false)
  expect(wrapper.get('[role="switch"]').attributes('disabled')).toBeDefined()
})
