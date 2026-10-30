/** 模型切换分隔线回归：只有实际开始输出的轮次显示标记，等待和失败不提前展示。 */
import { expect, it } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, h, shallowRef } from 'vue'
import { TooltipProvider } from 'reka-ui'
import MessageList from '../../components/MessageList.vue'
import type { ChatMessage } from '../../types'
import type { ModelIdentity } from '@/features/model-selection/types'

const first: ModelIdentity = {
  model_configuration_id: 'a',
  catalog_model_id: 'deepseek:flash',
  display_name: 'Flash',
}
const second: ModelIdentity = {
  model_configuration_id: 'b',
  catalog_model_id: 'deepseek:pro',
  display_name: 'Pro',
}

it('发送前与等待回复时没有分隔线，首段输出后显示，刷新重建仍只有一条', async () => {
  const messages = shallowRef<ChatMessage[]>([
    { id: 'a-user', role: 'user', model: first, blocks: [{ type: 'paragraph', text: '第一轮' }] },
  ])
  // 使用真实 Tooltip 与列表，验证界面顺序而非内部派生数组。
  const Host = defineComponent({
    setup: () => () =>
      h(
        TooltipProvider,
        {},
        {
          default: () =>
            h(MessageList, {
              messages: messages.value,
              conversationId: 'conversation',
            }),
        },
      ),
  })
  const page = mount(Host)
  expect(page.findAll('.model-change-notice')).toHaveLength(0)
  messages.value = [
    ...messages.value,
    {
      id: 'b-user',
      role: 'user',
      model: second,
      modelReplyStarted: false,
      blocks: [{ type: 'paragraph', text: '第二轮' }],
    },
  ]
  await flushPromises()
  expect(page.findAll('.model-change-notice')).toHaveLength(0)
  messages.value = messages.value.map((message) =>
    message.id === 'b-user' ? { ...message, modelReplyStarted: true } : message,
  )
  await flushPromises()
  expect(page.findAll('.model-change-notice')).toHaveLength(1)
  expect(page.get('.model-change-notice').text()).toContain('模型已从 Flash 切换为 Pro')
  const text = page.text()
  expect(text.indexOf('第一轮')).toBeLessThan(text.indexOf('模型已从'))
  expect(text.indexOf('模型已从')).toBeLessThan(text.indexOf('第二轮'))
  page.unmount()
  const restored = mount(Host)
  expect(restored.findAll('.model-change-notice')).toHaveLength(1)
  restored.unmount()
})

it('相同原生模型的参数或方案变化不重复提示，缺失历史身份时不伪造切换', () => {
  const page = mount(TooltipProvider, {
    slots: {
      default: () =>
        h(MessageList, {
          conversationId: 'old',
          messages: [
            { id: 'old', role: 'user', blocks: [] },
            {
              id: 'same',
              role: 'user',
              model: { ...second, model_configuration_id: 'another' },
              blocks: [],
            },
          ],
        }),
    },
  })
  expect(page.find('.model-change-notice').exists()).toBe(false)
  page.unmount()
})
