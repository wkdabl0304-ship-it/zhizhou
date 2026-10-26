/** 模型配置跨业务集成：验证受保护路由、配置默认到聊天发送及草稿和身份边界，HTTP 以契约替身隔离。 */
import { beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'
import App from '@/App.vue'
import { createAppRouter } from '@/router'
import { createTestPinia } from '@tests/support/vitest/mount'
import { authenticate } from '@tests/support/vitest/auth'
import { installMediaQuery } from '@tests/support/vitest/browser'
import { modelConfigData } from '@tests/support/data/model-config'
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

// 切换模型管理只更新主内容；保留侧栏 DOM、目录缓存、折叠状态，并能从原目录回到聊天。
it('模型管理与聊天共用导航实例，保留折叠状态和目录，选择会话后返回聊天', async () => {
  const pinia = createTestPinia(),
    data = modelConfigData()
  await authenticate(pinia, fetchMock)
  fetchMock.mockImplementation(async (input) => {
    const url = String(input)
    if (url.endsWith('/default')) return response(data.selected)
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
  await page.get('a[aria-label="模型管理"]').trigger('click')
  await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('models'))
  await flushPromises()
  expect(page.get('aside').element).toBe(sidebar)
  expect(page.get('.chat-shell').classes()).toContain('sidebar-collapsed')
  expect(page.get('a[aria-label="模型管理"]').attributes('aria-current')).toBe('page')
  expect(page.get('a[aria-label="模型管理"]').classes()).toContain('is-active')
  // 收起状态按原设计隐藏目录，展开后应直接复用已加载的会话。
  await page.get('button[aria-label="展开侧栏"]').trigger('click')
  expect(page.get('.conversation-item').text()).toContain('历史话题')
  expect(
    fetchMock.mock.calls.filter(([url]) => String(url).startsWith('/api/conversations?')),
  ).toHaveLength(1)
  await page.get('.conversation-item').trigger('click')
  await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('chat'))
  await flushPromises()
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
  await authenticate(pinia, fetchMock)
  fetchMock.mockImplementation(async (input) => {
    const url = String(input)
    if (url.endsWith('/default')) return response(data.selected)
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
  await authenticate(pinia, fetchMock)
  let selected = {
    ...data.selected,
    model_configuration_id: null as string | null,
    model: null as typeof data.model | null,
  }
  fetchMock.mockImplementation(async (input, init) => {
    const url = String(input)
    if (url === '/api/chat') return success('server-config-chat', '配置后的回复')
    if (url === '/api/model-config/default') {
      if (init?.method === 'PUT') selected = { ...data.selected, version: 2 }
      return response(selected)
    }
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
  await page.get('form').trigger('submit')
  expect(fetchMock.mock.calls.filter(([url]) => url === '/api/chat')).toHaveLength(0)
  expect(page.get('button[type="submit"]').attributes('disabled')).toBeDefined()
  await page.get('a[href="/models"]').trigger('click')
  await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('models'))
  await flushPromises()
  const select = page.findAll('button').find((button) => button.text() === '设为默认')!
  await select.trigger('click')
  await flushPromises()
  expect(page.text()).toContain('从下一轮聊天生效')
  expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/test'))).toBe(false)
  await router.push('/')
  await flushPromises()
  expect((page.get('textarea').element as HTMLTextAreaElement).value).toBe('配置前写下的想法')
  await page.get('form').trigger('submit')
  await flushPromises()
  expect(page.text()).toContain('配置后的回复')
  expect(page.text()).toContain('全局默认 · 长文分析')
  useAuthStore().logout()
  await flushPromises()
  expect(useModelConfigStore().selected).toBeNull()
  await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('login'))
})

it('默认读取失败保留草稿并可重试，窗口激活后同步不可用状态', async () => {
  const pinia = createTestPinia(),
    data = modelConfigData()
  await authenticate(pinia, fetchMock)
  fetchMock.mockImplementation(async (input) =>
    String(input).endsWith('/default')
      ? response(null, 500, 50000, '服务暂时不可用')
      : response({ items: [], next_cursor: null }),
  )
  const router = createAppRouter(createMemoryHistory())
  await router.push('/')
  const page = mount(App, { global: { plugins: [pinia, router] } })
  await flushPromises()
  await page.get('textarea').setValue('重试后保留的草稿')
  expect(page.get('button[type="submit"]').attributes('disabled')).toBeDefined()
  fetchMock.mockResolvedValueOnce(response(data.selected))
  await page
    .findAll('button')
    .find((button) => button.text() === '重试读取默认模型')!
    .trigger('click')
  await flushPromises()
  expect(page.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
  fetchMock.mockResolvedValueOnce(
    response({ ...data.selected, model: { ...data.model, available: false, catalog: null } }),
  )
  window.dispatchEvent(new Event('focus'))
  await flushPromises()
  expect(page.text()).toContain('默认模型暂不可用')
  expect((page.get('textarea').element as HTMLTextAreaElement).value).toBe('重试后保留的草稿')
  await page.get('form').trigger('submit')
  expect(fetchMock.mock.calls.some(([url]) => url === '/api/chat')).toBe(false)
})

// 页面仍缓存可用默认时，服务端拒绝发送也应同步共享配置，不要求用户退出或刷新页面。
it('默认被外部清除后发送失败会更新状态，保留登录并阻止继续发送', async () => {
  const pinia = createTestPinia(),
    data = modelConfigData()
  await authenticate(pinia, fetchMock)
  let cleared = false
  fetchMock.mockImplementation(async (input) => {
    const url = String(input)
    if (url === '/api/chat') return response(null, 503, 50301, '尚未配置默认模型')
    if (url.endsWith('/default'))
      return response(
        cleared
          ? { ...data.selected, version: 2, model_configuration_id: null, model: null }
          : data.selected,
      )
    return response({ items: [], next_cursor: null })
  })
  const router = createAppRouter(createMemoryHistory())
  await router.push('/')
  const page = mount(App, { global: { plugins: [pinia, router] } })
  await flushPromises()
  cleared = true
  await page.get('textarea').setValue('默认已被其他用户清除')
  await page.get('form').trigger('submit')
  await flushPromises()
  expect(page.get('[aria-label="聊天模型状态"]').text()).toContain('尚未配置默认模型')
  expect(useAuthStore().isAuthenticated).toBe(true)
  expect(router.currentRoute.value.name).toBe('chat')
  await page.get('textarea').setValue('配置恢复前的草稿')
  expect(page.get('button[type="submit"]').attributes('disabled')).toBeDefined()
  await page.get('form').trigger('submit')
  expect(fetchMock.mock.calls.filter(([url]) => url === '/api/chat')).toHaveLength(1)
  expect((page.get('textarea').element as HTMLTextAreaElement).value).toBe('配置恢复前的草稿')
})
