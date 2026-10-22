/** 认证测试数据：提供公开身份和独立 HTTP 响应，不连接数据库或保存真实凭据。 */
import type { AuthUser, LoginResult } from '../types'

export const USER: AuthUser = {
  id: '56e41c75-6e07-4d4c-85dd-e98d53ac68ac',
  username: 'lin_zhou',
  role: 'user',
}
export const CREDENTIALS = { username: USER.username, password: ' test password ' }
export const LOGIN: LoginResult = {
  access_token: 'test-access-token',
  token_type: 'bearer',
  expires_in: 7200,
  user: USER,
}

/** 每次创建可单独读取的响应体，用于模拟后端的统一响应与 HTTP/业务失败。 */
export function response(data: unknown, status = 200, code = 0, message = '成功'): Response {
  return new Response(JSON.stringify({ code, message, data }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** 创建可显式完成的请求，验证退出、页面切换与迟到响应的竞争边界。 */
export function deferredResponse() {
  let resolve!: (value: Response) => void
  // 由测试决定请求结束时间，不依赖真实网络时序。
  const promise = new Promise<Response>((done) => {
    resolve = done
  })
  return { promise, resolve }
}
