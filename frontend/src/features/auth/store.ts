/** 登录状态：在当前标签页保存短期令牌，恢复时校验服务器身份，并在退出或到期时清理。 */
import { computed, onScopeDispose, ref } from 'vue'
import { defineStore } from 'pinia'
import { AuthApiError, currentUser, login as requestLogin } from './api'
import type { AuthUser, Credentials } from './types'

export const AUTH_STORAGE_KEY = 'zhizhou-auth'

/** 标签页内持久化的数据仅含令牌与到期时刻；公开身份由 /me 重新确认。 */
interface SavedSession {
  token: string
  expiresAt: number
}

/** 创建独立认证状态，不依赖聊天 store，跨页面身份边界由应用根组件协调。 */
export const useAuthStore = defineStore('auth', () => {
  const user = ref<AuthUser | null>(null)
  const session = ref<SavedSession | null>(null)
  const initialized = ref(false)
  const restoreError = ref('')
  const notice = ref('')
  const registeredUsername = ref('')
  const isAuthenticated = computed(() => user.value !== null && session.value !== null)
  const accessToken = computed(() => session.value?.token ?? '')
  let timer: ReturnType<typeof setTimeout> | undefined
  let restoring: Promise<void> | undefined
  let revision = 0

  /** 移除当前标签页凭据；存储被禁用时仍能结束内存中的登录状态。 */
  function clearSession(message = ''): void {
    revision += 1
    clearTimeout(timer)
    session.value = null
    user.value = null
    notice.value = message
    restoreError.value = ''
    try {
      sessionStorage.removeItem(AUTH_STORAGE_KEY)
    } catch {
      /* 存储不可用不阻止内存退出。 */
    }
  }

  /** 按令牌有效期结束界面登录状态；超长时长分段等待，避免浏览器定时器溢出。 */
  function scheduleExpiry(): void {
    clearTimeout(timer)
    if (!session.value) return
    const remaining = session.value.expiresAt - Date.now()
    if (remaining <= 0) {
      clearSession('登录已过期，请重新登录')
      return
    }
    timer = setTimeout(scheduleExpiry, Math.min(remaining, 2_147_483_647))
  }

  /** 从标签页读取并校验存储结构，不恢复密码，也不信任缓存中的用户身份。 */
  function readSession(): SavedSession | null {
    try {
      const raw = sessionStorage.getItem(AUTH_STORAGE_KEY)
      const data: unknown = raw ? JSON.parse(raw) : null
      if (
        data &&
        typeof data === 'object' &&
        'token' in data &&
        typeof data.token === 'string' &&
        data.token.trim() &&
        'expiresAt' in data &&
        typeof data.expiresAt === 'number' &&
        Number.isSafeInteger(data.expiresAt)
      )
        return { token: data.token, expiresAt: data.expiresAt }
    } catch {
      /* 破损或不可访问的存储回退到未登录。 */
    }
    return null
  }

  /** 恢复刷新后的身份，合并并发校验；临时网络失败保留令牌供用户显式重试。 */
  async function initialize(force = false): Promise<void> {
    if (restoring) return restoring
    if (initialized.value && !force) {
      scheduleExpiry()
      return
    }
    const version = revision
    restoring = (async () => {
      const saved = session.value ?? readSession()
      if (!saved) {
        clearSession()
        initialized.value = true
        return
      }
      if (saved.expiresAt <= Date.now()) {
        clearSession('登录已过期，请重新登录')
        initialized.value = true
        return
      }
      session.value = saved
      try {
        const identity = await currentUser(saved.token)
        if (version !== revision) return
        user.value = identity
        restoreError.value = ''
        scheduleExpiry()
      } catch (error) {
        if (version !== revision) return
        if (error instanceof AuthApiError && error.status === 401)
          clearSession('登录状态无效或已过期，请重新登录')
        else
          restoreError.value =
            error instanceof AuthApiError ? error.message : '无法验证登录状态，请稍后重试'
      } finally {
        initialized.value = true
      }
    })()
    try {
      await restoring
    } finally {
      restoring = undefined
    }
  }

  /** 验证本次凭据并建立登录状态；请求被取消或退出后才到达的响应不能重新登录。 */
  async function login(credentials: Credentials, signal?: AbortSignal): Promise<void> {
    const version = ++revision
    const result = await requestLogin(credentials, signal)
    if (signal?.aborted || version !== revision)
      throw new DOMException('登录请求已取消', 'AbortError')
    session.value = { token: result.access_token, expiresAt: Date.now() + result.expires_in * 1000 }
    user.value = result.user
    initialized.value = true
    notice.value = ''
    restoreError.value = ''
    registeredUsername.value = ''
    try {
      sessionStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(session.value))
    } catch {
      /* 退化为当前页面内存登录。 */
    }
    scheduleExpiry()
  }

  /** 结束当前浏览器登录；后端没有令牌撤销接口，不伪造服务端退出请求。 */
  function logout(): void {
    clearSession()
    registeredUsername.value = ''
    initialized.value = true
  }

  /** 为业务请求取得尚未到期的令牌；不向接口层暴露存储结构或密码。 */
  function requireToken(): string {
    scheduleExpiry()
    if (!isAuthenticated.value) throw new AuthApiError('登录已过期，请重新登录', 401)
    return accessToken.value
  }

  /** 接受当前令牌的服务端失效通知；旧请求的 401 不能退出后来登录的新账号。 */
  function invalidate(token: string): void {
    if (accessToken.value === token) clearSession('登录状态无效或已过期，请重新登录')
  }

  /** 将新注册账号带回登录表单，仅保存用户名；注册响应不会建立认证状态。 */
  function prepareLogin(username: string): void {
    registeredUsername.value = username
    notice.value = '账号创建成功，请登录。'
  }

  // store 销毁后释放定时器，并拒绝尚未完成的异步身份恢复和登录结果。
  onScopeDispose(() => {
    clearTimeout(timer)
    revision += 1
  })

  return {
    user,
    isAuthenticated,
    accessToken,
    requireToken,
    invalidate,
    initialized,
    restoreError,
    notice,
    registeredUsername,
    initialize,
    login,
    logout,
    prepareLogin,
  }
})
