/** 已登录业务请求：统一添加 Bearer、处理失效及安全错误，供会话 JSON 与聊天 SSE 共用。 */
import { useAuthStore } from '@/features/auth/store'

/** 对外可展示的接口失败，保留 HTTP 与业务码供状态层区分不存在、忙碌及认证失败。 */
export class ApiError extends Error {
  /** 创建不包含凭据或底层堆栈的业务错误。 */
  constructor(
    message: string,
    public readonly status = 0,
    public readonly code?: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/** 发送带当前身份的同源请求；失效通知只作用于本次使用的令牌，取消原样传播。 */
export async function authenticatedFetch(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
  const auth = useAuthStore()
  const token = auth.requireToken()
  const headers = new Headers(options.headers)
  headers.set('Authorization', `Bearer ${token}`)
  let response: Response
  try {
    response = await fetch(path, { ...options, headers: Object.fromEntries(headers.entries()) })
  } catch {
    if (options.signal?.aborted) throw new DOMException('请求已取消', 'AbortError')
    throw new ApiError('网络连接失败，请稍后重试')
  }
  if (response.status === 401) auth.invalidate(token)
  return response
}

/** 解析统一 JSON 响应，同时检查 HTTP 与业务状态；不把错误代理页当作成功数据。 */
export async function readEnvelope(response: Response): Promise<unknown> {
  let body: unknown
  try {
    body = await response.json()
  } catch {
    throw new ApiError('服务响应无效，请稍后重试', response.status)
  }
  if (!body || typeof body !== 'object' || !('code' in body) || !Number.isInteger(body.code))
    throw new ApiError('服务响应无效，请稍后重试', response.status)
  if (!response.ok || body.code !== 0) {
    const message =
      'message' in body && typeof body.message === 'string' && body.message.trim()
        ? body.message
        : '请求失败，请稍后重试'
    throw new ApiError(message, response.status, body.code as number)
  }
  if (!('data' in body)) throw new ApiError('服务响应无效，请稍后重试', response.status)
  return body.data
}
