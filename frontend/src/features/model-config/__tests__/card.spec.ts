/** 模型方案卡片回归：验证可用性、默认删除入口与仅对应当前版本的测试结论。 */
import { expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { modelConfigData } from '@tests/support/data/model-config'
import ModelCard from '../components/ModelCard.vue'

it('配置版本变化后旧测试不显示通过，目录不可用仍允许编辑和删除', async () => {
  const { model } = modelConfigData()
  const wrapper = mount(ModelCard, {
    props: {
      model,
      current: true,
      busy: false,
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
  expect(wrapper.text()).not.toContain('文本流通过')
  await wrapper.setProps({ model: { ...model, available: false } })
  expect(
    wrapper
      .findAll('button')
      .find((button) => button.text() === '测试')!
      .attributes('disabled'),
  ).toBeDefined()
  await wrapper
    .findAll('button')
    .find((button) => button.text() === '编辑')!
    .trigger('click')
  await wrapper
    .findAll('button')
    .find((button) => button.text() === '删除')!
    .trigger('click')
  expect(wrapper.emitted('edit')).toHaveLength(1)
  expect(wrapper.emitted('delete')).toHaveLength(1)
})
