/** 认证 HTTP 适配：调用注册、登录和身份接口，校验统一响应，不接入聊天或服务端会话。 */
import type { AuthUser, Credentials, LoginResult } from './types'

/** 可向页面展示的认证错误；保留 HTTP 状态和业务码以区分重名、凭据错误与令牌失效。 */
export class AuthApiError extends Error {
  /** 保存安全解释及协议状态，不包含请求密码和底层网络异常。 */
  constructor(
    message: string,
    public readonly status = 0,
    public readonly code?: number,
  ) {
    super(message)
    this.name = 'AuthApiError'
  }
}

/** 判断网络数据是否是对象，排除 null 和数组，便于逐字段校验。 */
function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

/** 验证公开用户数据，避免错误响应被持久化为登录身份。 */
function isUser(value: unknown): value is AuthUser {
  return (
    isRecord(value) &&
    typeof value.id === 'string' &&
    !!value.id.trim() &&
    typeof value.username === 'string' &&
    !!value.username.trim() &&
    (value.role === 'user' || value.role === 'super_admin')
  )
}

/** 读取一次统一 JSON 响应，HTTP 与业务失败均抛出 AuthApiError；取消信号原样传播。 */
async function request(path: string, options: RequestInit): Promise<unknown> {
  let response: Response
  try {
    response = await fetch(`/api/auth/${path}`, options)
  } catch {
    if (options.signal?.aborted) throw new DOMException('请求已取消', 'AbortError')
    throw new AuthApiError('网络连接失败，请稍后重试')
  }
  let body: unknown
  try {
    body = await response.json()
  } catch {
    if (options.signal?.aborted) throw new DOMException('请求已取消', 'AbortError')
    throw new AuthApiError('服务响应无效，请稍后重试', response.status)
  }
  if (!isRecord(body) || !Number.isInteger(body.code))
    throw new AuthApiError('服务响应无效，请稍后重试', response.status)
  if (!response.ok || body.code !== 0) {
    const message =
      typeof body.message === 'string' && body.message.trim()
        ? body.message
        : '认证请求失败，请稍后重试'
    throw new AuthApiError(message, response.status, body.code as number)
  }
  return body.data
}

/** 提交用户名密码并取得短期访问令牌；不修改任何浏览器登录状态。 */
export async function login(credentials: Credentials, signal?: AbortSignal): Promise<LoginResult> {
  const data = await request('login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(credentials),
    ...(signal ? { signal } : {}),
  })
  if (
    !isRecord(data) ||
    typeof data.access_token !== 'string' ||
    !data.access_token.trim() ||
    data.token_type !== 'bearer' ||
    typeof data.expires_in !== 'number' ||
    !Number.isSafeInteger(data.expires_in) ||
    data.expires_in <= 0 ||
    !Number.isSafeInteger(Date.now() + data.expires_in * 1000) ||
    !isUser(data.user)
  )
    throw new AuthApiError('登录响应格式无效，请稍后重试')
  return {
    access_token: data.access_token,
    token_type: 'bearer',
    expires_in: data.expires_in,
    user: data.user,
  }
}

/** 注册普通用户并返回公开身份；确认密码不传给后端，注册本身不等同于登录。 */
export async function register(credentials: Credentials, signal?: AbortSignal): Promise<AuthUser> {
  const data = await request('register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ ...credentials, role: 'user' }),
    ...(signal ? { signal } : {}),
  })
  if (!isUser(data)) throw new AuthApiError('注册响应格式无效，请稍后重试')
  return data
}

/** 使用当前令牌向服务器确认最新身份与账号状态，供页面刷新后的身份恢复使用。 */
export async function currentUser(token: string): Promise<AuthUser> {
  const data = await request('me', {
    method: 'GET',
    headers: { Accept: 'application/json', Authorization: `Bearer ${token}` },
  })
  if (!isUser(data)) throw new AuthApiError('身份响应格式无效，请稍后重试')
  return data
}
