/** 模型配置跨业务集成：验证受保护路由、配置默认到聊天发送及草稿和身份边界，HTTP 以契约替身隔离。 */
import { beforeEach, expect, it, vi } from 'vitest'
import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, type NavigationFailure, type Router } from 'vue-router'
import App from '@/App.vue'
import { createAppRouter } from '@/router'
import { createTestPinia } from '@tests/support/vitest/mount'
import { authenticate } from '@tests/support/vitest/auth'
import { installMediaQuery } from '@tests/support/vitest/browser'
import { modelConfigData } from '@tests/support/data/model-config'
import { modelOptionsData } from '@tests/support/data/model-selection'
import { response } from '@tests/support/vitest/http'
import { success } from '@tests/support/vitest/chat'
import { useAuthStore } from '@/features/auth/store'
import { useModelConfigStore } from '@/features/model-config/store'
import { useChatStore } from '@/features/chat/store'
import { A, info, turn } from '@tests/support/data/chat'

const fetchMock = vi.fn<typeof fetch>()
beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  installMediaQuery()
})

/** 等待真实用户操作触发的导航完成，包含守卫和懒加载，并在结束后移除临时监听。 */
async function followNavigation(router: Router, activate: () => unknown): Promise<void> {
  let stopNavigation!: () => void
  let stopError!: () => void
  const completed = new Promise<NavigationFailure | void>((resolve, reject) => {
    // 导航完成时保留取消或中断结果，不能将未进入目标页的情况当作成功。
    stopNavigation = router.afterEach((_to, _from, failure) => resolve(failure))
    // 懒加载或守卫异常直接使测试失败，避免等待一个永远不会成功的路由状态。
    stopError = router.onError(reject)
  })
  try {
    // 先安装导航监听再执行点击或退出；用例仍受测试运行器的整体超时约束。
    const [failure] = await Promise.all([completed, Promise.resolve().then(activate)])
    expect(failure).toBeUndefined()
    await flushPromises()
  } finally {
    stopNavigation()
    stopError()
  }
}

// 切换模型管理只更新主内容；保留侧栏 DOM、目录缓存、折叠状态，并能从原目录回到聊天。
it('模型管理与聊天共用导航实例，保留折叠状态和目录，选择会话后返回聊天', async () => {
  const pinia = createTestPinia(),
    data = modelConfigData()
  await authenticate(pinia, fetchMock, true)
  fetchMock.mockImplementation(async (input) => {
    const url = String(input)
    if (url.endsWith('/options')) return response(modelOptionsData())
    if (url.endsWith('/default')) return response(data.selected)
    if (url.includes('/catalog/models?')) return response([data.catalog])
    if (url.endsWith('/catalog/providers')) return response([data.brand])
    if (url.endsWith('/provider-configurations')) return response([data.provider])
    if (url.endsWith('/models')) return response([data.model])
    if (url.includes(`/conversations/${A}?`))
      return response({ conversation: info(), items: [turn()], next_cursor: null })
    return response({ items: [info()], next_cursor: null })
  })
  const router = createAppRouter(createMemoryHistory())
  await router.push('/')
  const page = mount(App, { global: { plugins: [pinia, router] } })
  await flushPromises()
  const sidebar = page.get('aside').element
  await page.get('textarea').setValue('不应误发到其他会话的草稿')
  await page.get('button[aria-label="收起侧栏"]').trigger('click')
  await followNavigation(router, () => page.get('a[aria-label="模型管理"]').trigger('click'))
  expect(router.currentRoute.value.name).toBe('models')
  expect(page.get('aside').element).toBe(sidebar)
  expect(page.get('.chat-shell').classes()).toContain('sidebar-collapsed')
  expect(page.get('a[aria-label="模型管理"]').attributes('aria-current')).toBe('page')
  expect(page.get('a[aria-label="模型管理"]').classes()).toContain('is-active')
  expect(page.find('.chat-header').exists()).toBe(false)
  expect(page.get('h1').text()).toBe('模型管理')
  expect(page.get('h2').text()).toContain('模型供应商')
  expect(page.find('a.config-link').exists()).toBe(false)
  // 收起状态按原设计隐藏目录，展开后应直接复用已加载的会话。
  await page.get('button[aria-label="展开侧栏"]').trigger('click')
  expect(page.get('.conversation-item').text()).toContain('历史话题')
  expect(
    fetchMock.mock.calls.filter(([url]) => String(url).startsWith('/api/conversations?')),
  ).toHaveLength(1)
  await followNavigation(router, () => page.get('.conversation-item').trigger('click'))
  expect(router.currentRoute.value.name).toBe('chat')
  expect(page.get('aside').element).toBe(sidebar)
  expect(page.get('a[aria-label="模型管理"]').classes()).not.toContain('is-active')
  expect(useChatStore().activeId).toBe(A)
  expect(page.text()).toContain('回答1')
  expect((page.get('textarea').element as HTMLTextAreaElement).value).toBe('')
})

// 模拟离页守卫取消；侧栏必须在导航成功后才改变聊天状态，避免丢失用户的草稿。
it('工作区导航被离页守卫取消时保留当前管理页与聊天草稿', async () => {
  const pinia = createTestPinia(),
    data = modelConfigData()
  await authenticate(pinia, fetchMock, true)
  fetchMock.mockImplementation(async (input) => {
    const url = String(input)
    if (url.endsWith('/options')) return response(modelOptionsData())
    if (url.endsWith('/default')) return response(data.selected)
    if (url.includes('/catalog/models?')) return response([data.catalog])
    if (url.endsWith('/catalog/providers')) return response([data.brand])
    if (url.endsWith('/provider-configurations')) return response([data.provider])
    if (url.endsWith('/models')) return response([data.model])
    return response({ items: [], next_cursor: null })
  })
  const router = createAppRouter(createMemoryHistory())
  await router.push('/models')
  const page = mount(App, { global: { plugins: [pinia, router] } })
  await flushPromises()
  const chat = useChatStore()
  chat.draft = '离页取消后保留的草稿'
  // 用真实导航守卫返回取消结果，验证工作区不会提前调用 startNew 清空状态。
  router.beforeEach((to) => (to.name === 'chat' ? false : undefined))
  await page.get('.new-chat-button').trigger('click')
  await flushPromises()
  expect(router.currentRoute.value.name).toBe('models')
  expect(chat.draft).toBe('离页取消后保留的草稿')
  expect(page.get('a[aria-label="模型管理"]').attributes('aria-current')).toBe('page')
})

it('未登录打开模型管理保留返回地址，未知管理子路径不进入认证循环', async () => {
  const pinia = createTestPinia(),
    router = createAppRouter(createMemoryHistory())
  useAuthStore(pinia)
  await router.push('/models?from=bookmark')
  const page = mount(App, { global: { plugins: [pinia, router] } })
  await flushPromises()
  expect(router.currentRoute.value.name).toBe('login')
  expect(router.currentRoute.value.query.redirect).toBe('/models?from=bookmark')
  expect(fetchMock).not.toHaveBeenCalled()
  expect(page.find('textarea').exists()).toBe(false)
  await router.push('/models/missing')
  await flushPromises()
  expect(router.currentRoute.value.name).toBe('not-found')
  expect(fetchMock).not.toHaveBeenCalled()
})

it('无默认可写草稿但禁止发送，在管理页直接设默认后返回保留草稿并正常聊天', async () => {
  const pinia = createTestPinia(),
    data = modelConfigData()
  await authenticate(pinia, fetchMock, true)
  let selected = {
    ...data.selected,
    model_configuration_id: null as string | null,
    model: null as typeof data.model | null,
  }
  fetchMock.mockImplementation(async (input, init) => {
    const url = String(input)
    if (url === '/api/chat') return success('server-config-chat', '配置后的回复')
    if (url.endsWith('/options'))
      return response({
        ...modelOptionsData(),
        default_selection: selected.model ? modelOptionsData().default_selection : null,
      })
    if (url === '/api/model-config/default') {
      if (init?.method === 'PUT') selected = { ...data.selected, version: 2 }
      return response(selected)
    }
    if (url.includes('/catalog/models?')) return response([data.catalog])
    if (url.endsWith('/catalog/providers')) return response([data.brand])
    if (url.endsWith('/provider-configurations')) return response([data.provider])
    if (url.endsWith('/models')) return response([data.model])
    return response({ items: [], next_cursor: null })
  })
  const router = createAppRouter(createMemoryHistory())
  await router.push('/')
  const page = mount(App, { attachTo: document.body, global: { plugins: [pinia, router] } })
  await flushPromises()
  await page.get('textarea').setValue('配置前写下的想法')
  await page.get('form.chat-composer').trigger('submit')
  expect(fetchMock.mock.calls.filter(([url]) => url === '/api/chat')).toHaveLength(0)
  expect(page.get('.chat-composer button[type="submit"]').attributes('disabled')).toBeDefined()
  await followNavigation(router, () => page.get('a[href="/models"]').trigger('click'))
  expect(router.currentRoute.value.name).toBe('models')
  await page.get('[aria-label="配置 Anthropic"]').trigger('click')
  await flushPromises()
  const select = [...document.querySelectorAll('button')].find(
    (button) => button.textContent?.trim() === '设为默认',
  )!
  select.click()
  await flushPromises()
  // 默认保存通过真实请求及卡片状态确认；列表成功通知移除后，仍须验证用户操作确实生效。
  const updates = fetchMock.mock.calls.filter(
    ([url, init]) => url === '/api/model-config/default' && init?.method === 'PUT',
  )
  expect(updates).toHaveLength(1)
  expect(JSON.parse(String(updates[0]![1]?.body))).toEqual({
    version: 1,
    model_configuration_id: data.model.id,
  })
  const card = new DOMWrapper(document.body).get(
    `article[aria-label="模型方案：${data.model.name}"]`,
  )
  expect(card.findAll('.ui-tag').some((tag) => tag.text() === '当前默认')).toBe(true)
  expect(card.findAll('button').map((button) => button.text())).toContain('清除默认')
  expect(document.querySelector('.config-notice')).toBeNull()
  expect(document.body.textContent).not.toContain('用于尚未选择模型的会话')
  expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/test'))).toBe(false)
  await router.push('/')
  await flushPromises()
  expect((page.get('textarea').element as HTMLTextAreaElement).value).toBe('配置前写下的想法')
  await page.get('form.chat-composer').trigger('submit')
  await flushPromises()
  expect(page.text()).toContain('配置后的回复')
  expect(page.get('.chat-model-trigger').text()).toContain('长文分析')
  await followNavigation(router, () => useAuthStore().logout())
  expect(useModelConfigStore().selected).toBeNull()
  expect(router.currentRoute.value.name).toBe('login')
})

it('选项读取失败保留草稿并可重试，窗口激活后同步不可用状态', async () => {
  const pinia = createTestPinia()
  await authenticate(pinia, fetchMock, true)
  fetchMock.mockImplementation(async (input) =>
    String(input).endsWith('/options')
      ? response(null, 500, 50000, '服务暂时不可用')
      : response({ items: [], next_cursor: null }),
  )
  const router = createAppRouter(createMemoryHistory())
  await router.push('/')
  const page = mount(App, { global: { plugins: [pinia, router] } })
  await flushPromises()
  await page.get('textarea').setValue('重试后保留的草稿')
  expect(page.get('.chat-composer button[type="submit"]').attributes('disabled')).toBeDefined()
  fetchMock.mockResolvedValueOnce(response(modelOptionsData()))
  await page.get('.chat-model-trigger').trigger('click')
  await flushPromises()
  expect(document.body.textContent).not.toContain('刷新模型选项')
  expect(page.get('.chat-composer button[type="submit"]').attributes('disabled')).toBeUndefined()
  fetchMock.mockResolvedValueOnce(response({ default_selection: null, providers: [] }))
  window.dispatchEvent(new Event('focus'))
  await flushPromises()
  expect(document.body.textContent).toContain('暂无可用模型')
  expect((page.get('textarea').element as HTMLTextAreaElement).value).toBe('重试后保留的草稿')
  await page.get('form.chat-composer').trigger('submit')
  expect(fetchMock.mock.calls.some(([url]) => url === '/api/chat')).toBe(false)
})

// 默认仅初始化空选择；外部清除默认不能改写当前会话的已确认选择。
it('无全局默认仍可手动选方案发送，默认清除后已有会话继续使用原选择', async () => {
  const pinia = createTestPinia(),
    data = modelOptionsData()
  data.default_selection = null
  await authenticate(pinia, fetchMock, true)
  fetchMock.mockImplementation(async (input) => {
    if (String(input).endsWith('/options')) return response(data)
    if (input === '/api/chat') return success(A, '手动选择后的回复')
    return response({ items: [], next_cursor: null })
  })
  const router = createAppRouter(createMemoryHistory())
  await router.push('/')
  const page = mount(App, { global: { plugins: [pinia, router] } })
  await flushPromises()
  await page.get('textarea').setValue('没有默认也能发送')
  expect(page.get('.chat-composer button[type="submit"]').attributes('disabled')).toBeDefined()
  await page.get('.chat-model-trigger').trigger('click')
  await flushPromises()
  document
    .querySelector<HTMLButtonElement>(
      '[data-model-id="' + data.providers[0]!.models[0]!.model_configuration_id + '"]',
    )!
    .click()
  await flushPromises()
  expect(page.get('.chat-composer button[type="submit"]').attributes('disabled')).toBeUndefined()
  await page.get('form.chat-composer').trigger('submit')
  await flushPromises()
  const posted = fetchMock.mock.calls.find(([url]) => url === '/api/chat')!
  expect(JSON.parse(String(posted[1]?.body))).toEqual({
    message: '没有默认也能发送',
    model_selection: {
      model_configuration_id: data.providers[0]!.models[0]!.model_configuration_id,
      reasoning: { mode: 'budget', budget_tokens: 4096 },
    },
  })
  expect(page.text()).toContain('手动选择后的回复')
  fetchMock.mockImplementation(async (input) =>
    String(input).endsWith('/options')
      ? response(data)
      : response({
          conversation: {
            ...info(),
            model_selection: useChatStore().effectiveSelection,
            model_selection_version: 1,
            model_selection_issue: null,
          },
        }),
  )
  window.dispatchEvent(new Event('focus'))
  await flushPromises()
  expect(useChatStore().selectionReady).toBe(true)
  expect(useChatStore().effectiveSelection?.model_configuration_id).toBe(
    data.providers[0]!.models[0]!.model_configuration_id,
  )
  expect(useAuthStore().isAuthenticated).toBe(true)
})
