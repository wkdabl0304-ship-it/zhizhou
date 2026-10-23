/** 认证生命周期测试：隔离标签页存储与时钟，验证刷新恢复、到期、重试及迟到响应。 */
import { createTestPinia as createPinia } from '@tests/support/vitest/mount'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { disposePinia, setActivePinia, type Pinia } from 'pinia'
import { AUTH_STORAGE_KEY, useAuthStore } from '@/features/auth/store'
import { createAuthData } from '@tests/support/data/auth'
import { deferredResponse, response } from '@tests/support/vitest/http'

let { CREDENTIALS, LOGIN, USER } = createAuthData()
// 每例重建契约对象，避免响应修改影响其他测试。
beforeEach(() => {
  ;({ CREDENTIALS, LOGIN, USER } = createAuthData())
})

let pinia: Pinia
const fetchMock = vi.fn<typeof fetch>()
// 固定系统时间并隔离存储，测试只推进令牌生命周期所需的时钟。
beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  sessionStorage.clear()
  localStorage.clear()
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-22T10:00:00Z'))
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})
// 销毁 store 释放定时器后再恢复浏览器替身，避免跨用例的异步副作用。
afterEach(() => {
  disposePinia(pinia)
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.useRealTimers()
  sessionStorage.clear()
  localStorage.clear()
})

/** 模拟刷新前保存的短期令牌；不缓存用户名、角色或密码。 */
function saveSession(expiresAt = Date.now() + 60_000): void {
  sessionStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify({ token: LOGIN.access_token, expiresAt }))
}

describe('认证状态', () => {
  // 登录只在当前标签页保存令牌和有效期，退出同步结束内存与存储身份。
  it('登录不持久化密码或用户信息，退出清除凭据', async () => {
    fetchMock.mockResolvedValue(response(LOGIN))
    const auth = useAuthStore()
    await auth.login(CREDENTIALS)
    expect(auth.isAuthenticated).toBe(true)
    expect(auth.user).toEqual(USER)
    expect(JSON.parse(sessionStorage.getItem(AUTH_STORAGE_KEY)!)).toEqual({
      token: LOGIN.access_token,
      expiresAt: Date.now() + 7_200_000,
    })
    expect(localStorage.length).toBe(0)
    auth.logout()
    expect(auth.user).toBeNull()
    expect(auth.isAuthenticated).toBe(false)
    expect(sessionStorage.getItem(AUTH_STORAGE_KEY)).toBeNull()
    expect(vi.getTimerCount()).toBe(0)
  })

  // 并发守卫共享一次 /me 请求，刷新时不能直接信任缓存中的身份。
  it('刷新后合并身份恢复，身份通过 /me 确认后才登录', async () => {
    saveSession()
    const request = deferredResponse()
    fetchMock.mockReturnValue(request.promise)
    const auth = useAuthStore()
    const first = auth.initialize()
    const second = auth.initialize()
    expect(auth.isAuthenticated).toBe(false)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    request.resolve(response(USER))
    await Promise.all([first, second])
    expect(auth.user).toEqual(USER)
    expect(auth.isAuthenticated).toBe(true)
    expect(fetchMock.mock.calls[0]![1]?.headers).toMatchObject({
      Authorization: `Bearer ${LOGIN.access_token}`,
    })
  })

  // 无效或过期的本地数据直接清理，不额外请求后端。
  it.each(['malformed', 'expired', 'empty-token'])('本地 %s 凭据回退到未登录', async (kind) => {
    if (kind === 'malformed') sessionStorage.setItem(AUTH_STORAGE_KEY, 'broken json')
    if (kind === 'expired') saveSession(Date.now() - 1)
    if (kind === 'empty-token')
      sessionStorage.setItem(
        AUTH_STORAGE_KEY,
        JSON.stringify({ token: '', expiresAt: Date.now() + 60_000 }),
      )
    const auth = useAuthStore()
    await auth.initialize()
    expect(auth.isAuthenticated).toBe(false)
    expect(sessionStorage.getItem(AUTH_STORAGE_KEY)).toBeNull()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  // 服务器确认令牌失效时清除凭据；网络故障保留凭据并允许显式重试。
  it('401 清理令牌，临时网络错误保留令牌并可重试', async () => {
    saveSession()
    fetchMock.mockResolvedValueOnce(response(null, 401, 40101, '登录已过期'))
    const auth = useAuthStore()
    await auth.initialize()
    expect(sessionStorage.getItem(AUTH_STORAGE_KEY)).toBeNull()
    expect(auth.notice).toContain('重新登录')
    saveSession()
    fetchMock.mockRejectedValueOnce(new TypeError('offline'))
    await auth.initialize(true)
    expect(auth.isAuthenticated).toBe(false)
    expect(auth.restoreError).toContain('网络连接失败')
    expect(sessionStorage.getItem(AUTH_STORAGE_KEY)).not.toBeNull()
    fetchMock.mockResolvedValueOnce(response(USER))
    await auth.initialize(true)
    expect(auth.isAuthenticated).toBe(true)
    expect(auth.restoreError).toBe('')
  })

  // 界面在令牌到期时自动失去身份，不依赖下一次导航。
  it('令牌到期自动退出并提示重新登录', async () => {
    fetchMock.mockResolvedValue(response({ ...LOGIN, expires_in: 2 }))
    const auth = useAuthStore()
    await auth.login(CREDENTIALS)
    await vi.advanceTimersByTimeAsync(1999)
    expect(auth.isAuthenticated).toBe(true)
    await vi.advanceTimersByTimeAsync(1)
    expect(auth.isAuthenticated).toBe(false)
    expect(auth.notice).toContain('过期')
    expect(sessionStorage.getItem(AUTH_STORAGE_KEY)).toBeNull()
  })

  // 浏览器拒绝持久化时仍可在本页登录和退出，异常不得阻断表单流程。
  it('存储不可写时退化为内存登录', async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('denied')
    })
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new DOMException('denied')
    })
    fetchMock.mockResolvedValue(response(LOGIN))
    const auth = useAuthStore()
    await auth.login(CREDENTIALS)
    expect(auth.isAuthenticated).toBe(true)
    expect(() => auth.logout()).not.toThrow()
    expect(auth.isAuthenticated).toBe(false)
  })

  // 退出后的网络响应不能再次创建身份，避免用户放弃的请求重新登录。
  it.each([
    ['login', 'AbortError'],
    ['restore', undefined],
  ])('退出后忽略迟到的 %s 结果', async (kind, expectedError) => {
    const request = deferredResponse()
    fetchMock.mockReturnValue(request.promise)
    const auth = useAuthStore()
    if (kind === 'restore') saveSession()
    const pending = kind === 'login' ? auth.login(CREDENTIALS) : auth.initialize()
    // 先挂上拒绝处理器，防止故意取消的登录被报告为未处理异常。
    const result = pending.catch((error: unknown) => error)
    auth.logout()
    request.resolve(response(kind === 'login' ? LOGIN : USER))
    const outcome = await result
    expect((outcome as DOMException | undefined)?.name).toBe(expectedError)
    expect(auth.isAuthenticated).toBe(false)
    expect(auth.user).toBeNull()
    expect(sessionStorage.getItem(AUTH_STORAGE_KEY)).toBeNull()
  })
})
