/** 认证页面集成：使用真实路由、根组件和状态，验证注册登录与退出，网络仅使用契约替身。 */
import { createTestPinia as createPinia } from '@tests/support/vitest/mount'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { disposePinia, setActivePinia, type Pinia } from 'pinia'
import { createMemoryHistory, type Router } from 'vue-router'
import App from '@/App.vue'
import { createAppRouter } from '@/router/index'
import { useChatStore } from '@/features/chat/store'
import { AUTH_STORAGE_KEY, useAuthStore } from '@/features/auth/store'
import { modelConfigData } from '@tests/support/data/model-config'
import { createAuthData } from '@tests/support/data/auth'
import { deferredResponse, response } from '@tests/support/vitest/http'

let { CREDENTIALS, LOGIN, USER } = createAuthData()
// 每例重建契约对象，避免响应修改影响其他测试。
beforeEach(() => {
  ;({ CREDENTIALS, LOGIN, USER } = createAuthData())
})

let pinia: Pinia
let router: Router
let wrapper: VueWrapper | undefined
const fetchMock = vi.fn<typeof fetch>()
// 使用内存历史隔离地址变化；媒体替身只提供聊天页需要的浏览器监听接口。
beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  router = createAppRouter(createMemoryHistory())
  sessionStorage.clear()
  localStorage.clear()
  fetchMock.mockReset()
  // 认证成功进入真实工作区后允许读取空会话目录，不把该请求误当成认证调用。
  fetchMock.mockImplementation(async (url) =>
    response(
      String(url) === '/api/model-config/default'
        ? modelConfigData().selected
        : { items: [], next_cursor: null },
    ),
  )
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('matchMedia', () => ({
    matches: false,
    addEventListener: vi.fn<() => void>(),
    removeEventListener: vi.fn<() => void>(),
  }))
})
// 先卸载页面释放视口监听，再销毁 store 定时器与路由历史。
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  disposePinia(pinia)
  router.options.history.destroy()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  sessionStorage.clear()
  localStorage.clear()
  delete document.documentElement.dataset.theme
  document.documentElement.style.colorScheme = ''
})

/** 等待路由懒加载结束后挂载完整应用，保留真实守卫及身份变化监听。 */
async function open(path: string): Promise<VueWrapper> {
  await router.push(path)
  await router.isReady()
  wrapper = mount(App, { global: { plugins: [pinia, router] } })
  await flushPromises()
  return wrapper
}

/** 填写当前认证页面并提交，不通过直接调用 store 绕过表单验证。 */
async function submitForm(page: VueWrapper, register = false): Promise<void> {
  await page.get('[name="username"]').setValue(CREDENTIALS.username)
  await page.get('[name="password"]').setValue(CREDENTIALS.password)
  if (register) await page.get('[name="confirmation"]').setValue(CREDENTIALS.password)
  await page.get('form').trigger('submit')
  await flushPromises()
}

describe('认证页面与工作区边界', () => {
  // 未登录不能进入聊天，开发预览保持可独立打开。
  it('保护工作区并保留原地址，开发预览不要求登录', async () => {
    const page = await open('/?from=bookmark')
    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/?from=bookmark')
    expect(page.get('h2').text()).toBe('欢迎回来')
    expect(fetchMock).not.toHaveBeenCalled()
    await router.push('/dev/ui')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('components')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  // 注册仅创建普通账号，回登录预填用户名；只有后续登录才进入工作区。
  it('注册成功回登录，登录显示真实账号，退出清空本页聊天', async () => {
    fetchMock.mockResolvedValueOnce(response(USER)).mockResolvedValueOnce(response(LOGIN))
    const page = await open('/register')
    expect(page.get('h1').text()).toContain('心有山海')
    await submitForm(page, true)
    expect(router.currentRoute.value.name).toBe('login')
    expect(page.text()).toContain('账号创建成功')
    expect((page.get('[name="username"]').element as HTMLInputElement).value).toBe(USER.username)
    expect((page.get('[name="password"]').element as HTMLInputElement).value).toBe('')
    expect(sessionStorage.getItem(AUTH_STORAGE_KEY)).toBeNull()
    await submitForm(page)
    expect(router.currentRoute.value.name).toBe('chat')
    expect(page.text()).toContain(USER.username)
    const chat = useChatStore()
    chat.conversations = [
      { id: 'local-conversation', title: '上一账号的临时内容', group: '今天', messages: [] },
    ]
    chat.activeId = 'local-conversation'
    await page.get('[aria-label="退出登录"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('login')
    expect(chat.conversations).toHaveLength(0)
    expect(chat.activeId).toBeNull()
    expect(sessionStorage.getItem(AUTH_STORAGE_KEY)).toBeNull()
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/api/auth/register',
      '/api/auth/login',
      '/api/model-config/default',
      '/api/conversations?limit=20',
    ])
  })

  // 刷新通过 /me 恢复真实身份，已登录访问认证页时不形成循环或外部跳转。
  it('刷新验证身份，已登录访问登录页回到站内工作区', async () => {
    sessionStorage.setItem(
      AUTH_STORAGE_KEY,
      JSON.stringify({ token: LOGIN.access_token, expiresAt: Date.now() + 60_000 }),
    )
    fetchMock.mockResolvedValueOnce(response(USER))
    const page = await open('/login?redirect=https://evil.test')
    expect(router.currentRoute.value.name).toBe('chat')
    expect(page.text()).toContain(USER.username)
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/api/auth/me',
      '/api/model-config/default',
      '/api/conversations?limit=20',
    ])
    await router.push('/register')
    expect(router.currentRoute.value.name).toBe('chat')
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  // 账号重复属于字段错误；凭据错误属于登录请求失败，均保留表单重试入口。
  it('展示重名与错误密码提示，不建立登录', async () => {
    fetchMock
      .mockResolvedValueOnce(response(null, 200, 20001, '用户名已存在'))
      .mockResolvedValueOnce(response(null, 401, 40102, '用户名或密码错误'))
    const page = await open('/register')
    await submitForm(page, true)
    expect(page.get('[name="username"]').attributes('aria-invalid')).toBe('true')
    expect(page.text()).toContain('用户名已存在')
    await router.push('/login')
    await flushPromises()
    await submitForm(page)
    expect(page.text()).toContain('用户名或密码错误')
    expect(router.currentRoute.value.name).toBe('login')
    expect(useAuthStore().isAuthenticated).toBe(false)
  })

  // 主动切换页面会取消在途登录，旧响应不能覆盖注册页或写入令牌。
  it('切换认证页面取消请求并清空密码，迟到登录结果被忽略', async () => {
    const request = deferredResponse()
    fetchMock.mockReturnValue(request.promise)
    const page = await open('/login')
    await submitForm(page)
    const signal = fetchMock.mock.calls[0]![1]?.signal
    expect(signal?.aborted).toBe(false)
    await router.push('/register')
    await flushPromises()
    expect(signal?.aborted).toBe(true)
    request.resolve(response(LOGIN))
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('register')
    expect(useAuthStore().isAuthenticated).toBe(false)
    expect((page.get('[name="password"]').element as HTMLInputElement).value).toBe('')
    expect(page.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
  })

  // 临时断网不丢掉可重试的令牌，也不能把未验证的缓存当作身份放行。
  it('刷新断网时展示重试入口，重试验证后进入工作区', async () => {
    sessionStorage.setItem(
      AUTH_STORAGE_KEY,
      JSON.stringify({ token: LOGIN.access_token, expiresAt: Date.now() + 60_000 }),
    )
    fetchMock.mockRejectedValueOnce(new TypeError('offline')).mockResolvedValueOnce(response(USER))
    const page = await open('/')
    expect(router.currentRoute.value.name).toBe('login')
    expect(page.text()).toContain('网络连接失败')
    const retry = page.findAll('button').find((button) => button.text() === '重试验证')!
    await retry.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('chat')
    expect(useAuthStore().user).toEqual(USER)
  })
})
