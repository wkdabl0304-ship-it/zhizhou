/** 认证测试数据：提供公开身份和独立 HTTP 响应，不连接数据库或保存真实凭据。 */
import type { AuthUser, LoginResult } from '../types'
export { response, deferredResponse } from '@/__tests__/helpers/http'

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
