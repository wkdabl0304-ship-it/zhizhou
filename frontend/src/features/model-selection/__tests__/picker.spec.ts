/** 聊天选择控件回归：无默认手动选择、固定值只读、预算确认与已有会话立即保存。 */
import { beforeEach, expect, it, vi } from 'vitest'
import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import { createTestPinia } from '@tests/support/vitest/mount'
import { authenticate } from '@tests/support/vitest/auth'
import { deferredResponse, response } from '@tests/support/vitest/http'
import { modelOptionsData } from '@tests/support/data/model-selection'
import { A, B, info } from '@tests/support/data/chat'
import { useChatStore } from '@/features/chat/store'
import ChatModelSelector from '../components/ChatModelSelector.vue'
const fetchMock = vi.fn<typeof fetch>()
beforeEach(async () => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  await authenticate(createTestPinia(), fetchMock)
})
/** 挂载真实选择器，路由链接仅替换为不导航的锚点，所有输入及 HTTP 仍为真实实现。 */
async function picker() {
  const page = mount(ChatModelSelector, {
    attachTo: document.body,
    global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
  await flushPromises()
  await page.get('.chat-model-trigger').trigger('click')
  await flushPromises()
  return new DOMWrapper(document.body)
}
it('没有全局默认也能手动选择固定方案，选择草稿不污染允许范围或发起 PATCH', async () => {
  const data = modelOptionsData()
  data.default_selection = null
  data.providers[0]!.models[0]!.reasoning_control = { mode: 'fixed', default: { mode: 'off' } }
  fetchMock.mockResolvedValue(response(data))
  const page = await picker()
  await flushPromises()
  expect(useChatStore().selectionReady).toBe(false)
  await page
    .get('[data-model-id="' + data.providers[0]!.models[0]!.model_configuration_id + '"]')
    .trigger('click')
  await flushPromises()
  expect(document.querySelector('.chat-model-popover')).toBeNull()
  await page.get('.chat-model-trigger').trigger('click')
  await flushPromises()
  expect(page.text()).toContain('固定推理设置')
  expect(page.find('[name="chat_reasoning_mode"]').exists()).toBe(false)
  expect(useChatStore().selectionReady).toBe(true)
  expect(useChatStore().effectiveSelection?.reasoning).toEqual({ mode: 'off' })
  expect(fetchMock.mock.calls).toHaveLength(1)
})
it('预算未完成不发送请求，确认有效整数才保存，并使用确认版本更新状态', async () => {
  const data = modelOptionsData(),
    chat = useChatStore()
  chat.conversations = [
    {
      id: A,
      title: '已有会话',
      group: '今天',
      messages: [],
      persisted: true,
      loaded: true,
      modelSelection: data.default_selection,
      modelSelectionVersion: 3,
    },
  ]
  chat.activeId = A
  fetchMock.mockImplementation(async (url, init) => {
    if (String(url).endsWith('/options')) return response(data)
    if (init?.method === 'PATCH') {
      const body = JSON.parse(String(init.body))
      return response({
        ...info(),
        model_selection: body.model_selection,
        model_selection_version: 4,
        model_selection_issue: null,
      })
    }
    return response({
      conversation: {
        ...info(),
        model_selection: data.default_selection,
        model_selection_version: 3,
        model_selection_issue: null,
      },
    })
  })
  const page = await picker()
  await flushPromises()
  await page.get('[name="chat_budget"]').setValue('1.5')
  await page.get('form').trigger('submit')
  await flushPromises()
  expect(page.text()).toContain('整数')
  expect(chat.selectionReady).toBe(false)
  expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'PATCH')).toHaveLength(0)
  await page.get('[name="chat_budget"]').setValue('8192')
  await page.get('form').trigger('submit')
  await flushPromises()
  expect(chat.activeConversation?.modelSelectionVersion).toBe(4)
  const write = fetchMock.mock.calls.find(([, init]) => init?.method === 'PATCH')!
  expect(JSON.parse(String(write[1]?.body)).model_selection_version).toBe(3)
  expect(chat.effectiveSelection?.reasoning).toEqual({ mode: 'budget', budget_tokens: 8192 })
  expect(chat.selectionReady).toBe(true)
})

it('原会话保存迟到时，不重置另一会话尚未确认的预算草稿', async () => {
  const data = modelOptionsData(),
    chat = useChatStore(),
    saving = deferredResponse()
  chat.conversations = [A, B].map((id) => ({
    id,
    title: id,
    group: '今天',
    messages: [],
    persisted: true,
    loaded: true,
    modelSelection: structuredClone(data.default_selection),
    modelSelectionVersion: 3,
  }))
  chat.activeId = A
  fetchMock.mockImplementation(async (url, init) => {
    if (init?.method === 'PATCH') return saving.promise
    if (String(url).endsWith('/options')) return response(data)
    return response({
      conversation: {
        ...info(),
        model_selection: data.default_selection,
        model_selection_version: 3,
        model_selection_issue: null,
      },
    })
  })
  const page = await picker()
  await flushPromises()
  await page.get('[name="chat_budget"]').setValue('8192')
  await page.get('form').trigger('submit')
  await chat.select(B)
  await flushPromises()
  await page.get('.chat-model-trigger').trigger('click')
  await flushPromises()
  await page.get('[name="chat_budget"]').setValue('1024')
  saving.resolve(
    response({
      ...info(),
      model_selection: {
        ...data.default_selection,
        reasoning: { mode: 'budget', budget_tokens: 8192 },
      },
      model_selection_version: 4,
      model_selection_issue: null,
    }),
  )
  await flushPromises()
  expect(chat.activeId).toBe(B)
  expect((page.get('[name="chat_budget"]').element as HTMLInputElement).value).toBe('1024')
  expect(chat.selectionEditing).toBe(true)
  expect(chat.effectiveSelection?.reasoning).toEqual({ mode: 'budget', budget_tokens: 4096 })
  expect(chat.conversations.find((row) => row.id === A)?.modelSelectionVersion).toBe(4)
})

it('关闭下拉取消未确认预算，恢复可发送状态且不提交聊天或配置', async () => {
  const data = modelOptionsData()
  fetchMock.mockResolvedValue(response(data))
  const page = await picker()
  const chat = useChatStore()
  chat.draft = '选择模型不能误发的消息'
  await page.get('[name="chat_budget"]').setValue('1024')
  expect(chat.selectionEditing).toBe(true)
  await page.get('.chat-model-trigger').trigger('click')
  await flushPromises()
  expect(document.querySelector('.chat-model-popover')).toBeNull()
  expect(chat.selectionEditing).toBe(false)
  expect(chat.effectiveSelection?.reasoning).toEqual(data.default_selection?.reasoning)
  expect(chat.draft).toBe('选择模型不能误发的消息')
  expect(
    fetchMock.mock.calls.every(([, init]) => init?.method !== 'PATCH' && init?.method !== 'POST'),
  ).toBe(true)
})

it('键盘浏览只移动焦点，不隐式保存模型选择', async () => {
  const data = modelOptionsData()
  data.default_selection = null
  data.providers[0]!.models.push({
    ...structuredClone(data.providers[0]!.models[0]!),
    model_configuration_id: 'second',
    name: '另一个模型',
  })
  fetchMock.mockResolvedValue(response(data))
  const page = await picker()
  const option = page.get('[role="option"]')
  ;(option.element as HTMLButtonElement).focus()
  await page.get('[role="listbox"]').trigger('keydown', { key: 'ArrowDown' })
  expect(document.activeElement).toBe(page.get('[data-model-id="second"]').element)
  expect(useChatStore().effectiveSelection).toBeNull()
  expect(fetchMock.mock.calls.every(([, init]) => init?.method !== 'PATCH')).toBe(true)
})

it('旧的冲突提醒不能遮住后来出现的推理范围失效原因', async () => {
  const data = modelOptionsData()
  fetchMock.mockResolvedValue(response(data))
  const page = await picker()
  const chat = useChatStore()
  chat.selectionNotice = '之前的会话选择发生冲突，请确认'
  chat.conversations = [
    {
      id: A,
      title: '范围已收紧',
      group: '今天',
      messages: [],
      loaded: true,
      persisted: true,
      modelSelection: data.default_selection,
      modelSelectionVersion: 3,
      modelSelectionIssue: 'reasoning_not_allowed',
    },
  ]
  chat.activeId = A
  await flushPromises()
  expect(page.text()).toContain('原推理设置超出当前限制')
  expect(page.text()).toContain('之前的会话选择发生冲突')
  expect(chat.selectionReady).toBe(false)
  await page.get('.chat-model-trigger').trigger('click')
  await flushPromises()
  expect(page.get('[role="alert"]').text()).toContain('原推理设置超出当前限制')
})
