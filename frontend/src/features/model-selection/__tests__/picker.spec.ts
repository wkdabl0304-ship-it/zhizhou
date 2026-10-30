/** 聊天选择控件回归：无默认手动选择、固定值只读、预算确认与已有会话立即保存。 */
import { beforeEach, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import { createTestPinia } from '@tests/support/vitest/mount'
import { authenticate } from '@tests/support/vitest/auth'
import { deferredResponse, response } from '@tests/support/vitest/http'
import { modelOptionsData } from '@tests/support/data/model-selection'
import { A, B, info } from '@tests/support/data/chat'
import { useChatStore } from '@/features/chat/store'
import ChatModelSelector from '../components/ChatModelSelector.vue'
import ChatReasoningControl from '../components/ChatReasoningControl.vue'
import type { ConcreteReasoning } from '../types'
const fetchMock = vi.fn<typeof fetch>()
beforeEach(async () => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  await authenticate(createTestPinia(), fetchMock)
})
/** 挂载真实选择器，路由链接仅替换为不导航的锚点，所有输入及 HTTP 仍为真实实现。 */
async function picker(kind: 'models' | 'reasoning' = 'models') {
  const Host = defineComponent({
    setup: () => () => h('div', [h(ChatModelSelector), h(ChatReasoningControl)]),
  })
  const page = mount(Host, {
    attachTo: document.body,
    global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
  await flushPromises()
  await page
    .get(kind === 'models' ? '.chat-model-trigger' : '.reasoning-strength-trigger')
    .trigger('click')
  await flushPromises()
  return new DOMWrapper(document.body)
}
it('没有全局默认也能手动选择固定方案，选择草稿不污染允许范围或发起 PATCH', async () => {
  const data = modelOptionsData()
  data.default_selection = null
  data.providers[0]!.models[0]!.reasoning_control = { mode: 'fixed', default: { mode: 'off' } }
  fetchMock.mockImplementation(async () => response(data))
  const page = await picker()
  await flushPromises()
  expect(useChatStore().selectionReady).toBe(false)
  expect(page.text()).not.toContain('请选择模型方案')
  expect(page.find('.chat-model-menu-heading a').exists()).toBe(false)
  await page
    .get('[data-model-id="' + data.providers[0]!.models[0]!.model_configuration_id + '"]')
    .trigger('click')
  await flushPromises()
  expect(document.querySelector('.chat-model-popover')).toBeNull()
  await page.get('.chat-model-trigger').trigger('click')
  await flushPromises()
  expect(page.find('[role="switch"]').exists()).toBe(false)
  expect(page.get('.reasoning-strength-trigger').attributes('disabled')).toBeDefined()
  expect(page.get('.reasoning-strength-trigger').text()).toContain('关闭')
  expect(page.find('[name="chat_reasoning_mode"]').exists()).toBe(false)
  expect(useChatStore().selectionReady).toBe(true)
  expect(useChatStore().effectiveSelection?.reasoning).toEqual({ mode: 'off' })
  expect(
    fetchMock.mock.calls.every(([, options]) => !options?.method || options.method === 'GET'),
  ).toBe(true)
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
  const page = await picker('reasoning')
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
  const page = await picker('reasoning')
  await flushPromises()
  await page.get('[name="chat_budget"]').setValue('8192')
  await page.get('form').trigger('submit')
  await chat.select(B)
  await flushPromises()
  await page.get('.reasoning-strength-trigger').trigger('click')
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
  fetchMock.mockImplementation(async () => response(data))
  const page = await picker('reasoning')
  const chat = useChatStore()
  chat.draft = '选择模型不能误发的消息'
  await page.get('[name="chat_budget"]').setValue('1024')
  expect(chat.selectionEditing).toBe(true)
  await page.get('.reasoning-strength-trigger').trigger('click')
  await flushPromises()
  expect(document.querySelector('.reasoning-popover')).toBeNull()
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
  fetchMock.mockImplementation(async () => response(data))
  const page = await picker()
  const option = page.get('[role="option"]')
  const listbox = page.get<HTMLElement>('[role="listbox"]')
  // 管理链接移到标题后，打开菜单仍进入列表；从容器向上可直接到最后一个模型。
  await vi.waitFor(() =>
    expect(
      listbox.element === document.activeElement ||
        listbox.element.contains(document.activeElement),
    ).toBe(true),
  )
  listbox.element.focus()
  await listbox.trigger('keydown', { key: 'ArrowUp' })
  expect(document.activeElement).toBe(page.get('[data-model-id="second"]').element)
  await listbox.trigger('keydown', { key: 'Home' })
  expect(document.activeElement).toBe(option.element)
  await listbox.trigger('keydown', { key: 'ArrowDown' })
  expect(document.activeElement).toBe(page.get('[data-model-id="second"]').element)
  expect(useChatStore().effectiveSelection).toBeNull()
  expect(fetchMock.mock.calls.every(([, init]) => init?.method !== 'PATCH')).toBe(true)
})

it('自动恢复失败时保留失效原因与重试错误，旧冲突提醒不能遮住真实问题', async () => {
  const data = modelOptionsData()
  fetchMock.mockImplementation(async (url, init) =>
    init?.method === 'PATCH'
      ? response(null, 503, 50301, '自动恢复暂不可用')
      : response(
          String(url).endsWith('/options')
            ? data
            : {
                conversation: {
                  ...info(),
                  model_selection: data.default_selection,
                  model_selection_version: 3,
                  model_selection_issue: 'reasoning_not_allowed',
                },
              },
        ),
  )
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

it('预算滑块最左关闭思考，右移重新启用，关闭后浮层和入口仍保留', async () => {
  const data = modelOptionsData()
  fetchMock.mockImplementation(async () => response(data))
  const page = await picker('reasoning')
  const slider = page.get<HTMLInputElement>('[aria-label="思考预算滑块"]')
  await slider.setValue('0')
  await flushPromises()
  expect(useChatStore().effectiveSelection?.reasoning).toEqual({ mode: 'off' })
  expect(page.find('.reasoning-popover').exists()).toBe(true)
  expect(page.get('.reasoning-strength-trigger').text()).toContain('关闭')
  await slider.setValue('1')
  await flushPromises()
  expect(useChatStore().effectiveSelection?.reasoning).toEqual({
    mode: 'budget',
    budget_tokens: 1024,
  })
  expect(page.find('[role="switch"]').exists()).toBe(false)
})

it('推理档位滑块只提供后端允许值，拖动不保存，释放后确认', async () => {
  const data = modelOptionsData()
  data.default_selection!.reasoning = { mode: 'effort', effort: 'low' }
  data.providers[0]!.models[0]!.reasoning_control = {
    mode: 'selectable',
    default: { mode: 'effort', effort: 'low' },
    allowed_modes: ['off', 'effort'],
    effort_options: ['low', 'high'],
    budget: null,
  }
  fetchMock.mockImplementation(async () => response(data))
  const page = await picker('reasoning')
  const slider = page.get<HTMLInputElement>('[aria-label="推理强度"]')
  expect(slider.attributes('max')).toBe('2')
  slider.element.value = '2'
  await slider.trigger('input')
  expect(useChatStore().effectiveSelection?.reasoning).toEqual({ mode: 'effort', effort: 'low' })
  expect(useChatStore().selectionReady).toBe(false)
  await slider.trigger('change')
  await flushPromises()
  expect(useChatStore().effectiveSelection?.reasoning).toEqual({ mode: 'effort', effort: 'high' })
  expect(page.find('.reasoning-popover').exists()).toBe(true)
  expect(useChatStore().selectionReady).toBe(true)
})

it.each<ConcreteReasoning>([
  { mode: 'effort', effort: 'high' },
  { mode: 'budget', budget_tokens: 4096 },
  { mode: 'off' },
])('唯一可用值 $mode 保持真实选择，开启时滑块靠右，关闭时靠左', async (selected) => {
  const data = modelOptionsData()
  data.default_selection!.reasoning = selected
  data.providers[0]!.models[0]!.reasoning_control = {
    mode: 'selectable',
    default: selected,
    allowed_modes: [selected.mode],
    effort_options: selected.mode === 'effort' ? [selected.effort] : [],
    budget:
      selected.mode === 'budget'
        ? { min: selected.budget_tokens, max: selected.budget_tokens }
        : null,
  }
  fetchMock.mockImplementation(async () => response(data))
  const page = await picker('reasoning')
  const slider = page.get<HTMLInputElement>('input[type="range"]')
  const enabled = selected.mode !== 'off'
  expect(slider.element.value).toBe(enabled ? slider.element.max : slider.element.min)
  expect(slider.element.disabled).toBe(true)
  expect(slider.attributes('style')).toContain(`--slider-progress: ${enabled ? 100 : 0}%`)
  expect(page.get('.reasoning-ticks').classes().includes('is-single-on')).toBe(enabled)
  expect(page.findAll('.reasoning-ticks > span')).toHaveLength(1)
  expect(useChatStore().effectiveSelection?.reasoning).toEqual(selected)
  expect(useChatStore().selectionReady).toBe(true)
  // 打开只读滑块不应写会话，也不能把显示轨道的端点当成新的业务档位。
  expect(
    fetchMock.mock.calls.every(([, options]) => !options?.method || options.method === 'GET'),
  ).toBe(true)
})

// 首段 start 将本地临时 ID 换成服务端 ID，仍是同一会话，不能因此关闭用户刚打开的模型菜单。
it('临时会话绑定服务端 ID 时保留模型菜单，切到另一会话才关闭', async () => {
  const data = modelOptionsData(),
    chat = useChatStore()
  fetchMock.mockImplementation(async () => response(data))
  chat.conversations = [
    {
      id: 'draft-local',
      title: '当前会话',
      group: '今天',
      messages: [],
      persisted: false,
      loaded: true,
    },
  ]
  chat.activeId = 'draft-local'
  const page = await picker()
  chat.conversations[0]!.id = A
  chat.activeId = A
  await flushPromises()
  expect(page.find('.chat-model-popover').exists()).toBe(true)
  chat.startNew()
  await flushPromises()
  expect(page.find('.chat-model-popover').exists()).toBe(false)
})

it('关闭档保存失败保留原确认值，取消滑块草稿后解除编辑锁', async () => {
  const data = modelOptionsData(),
    chat = useChatStore()
  chat.conversations = [
    {
      id: A,
      title: '当前会话',
      group: '今天',
      messages: [],
      persisted: true,
      loaded: true,
      modelSelection: data.default_selection,
      modelSelectionVersion: 1,
    },
  ]
  chat.activeId = A
  fetchMock.mockImplementation(async (url, options) =>
    options?.method === 'PATCH'
      ? response(null, 500, 50000, '保存失败')
      : String(url).endsWith('/options')
        ? response(data)
        : response({ conversation: info() }),
  )
  const page = await picker('reasoning')
  await page.get('[aria-label="思考预算滑块"]').setValue('0')
  await flushPromises()
  expect(chat.effectiveSelection?.reasoning).toEqual(data.default_selection?.reasoning)
  expect(chat.selectionEditing).toBe(true)
  await page.get('.reasoning-strength-trigger').trigger('click')
  await flushPromises()
  expect(chat.selectionEditing).toBe(false)
})

it('未开放关闭时最左仍是合法最低预算，不绕过供应商范围', async () => {
  const data = modelOptionsData()
  const control = data.providers[0]!.models[0]!.reasoning_control
  if (control.mode === 'selectable') control.allowed_modes = ['budget']
  fetchMock.mockImplementation(async () => response(data))
  const page = await picker('reasoning')
  await page.get('[aria-label="思考预算滑块"]').setValue('0')
  await flushPromises()
  expect(useChatStore().effectiveSelection?.reasoning).toEqual({
    mode: 'budget',
    budget_tokens: 1024,
  })
  expect(page.get('.reasoning-ticks').text()).not.toContain('关闭')
})
