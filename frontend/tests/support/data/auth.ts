/** 认证契约工厂：生成独立的虚构账号、凭据和登录响应，不包含网络或测试运行器。 */
import type { AuthUser, LoginResult } from '@/features/auth/types'

/** 返回一组关联的认证数据；各次调用不共享可变对象。 */
export function createAuthData() {
  const USER: AuthUser = {
    id: '56e41c75-6e07-4d4c-85dd-e98d53ac68ac',
    username: 'lin_zhou',
    role: 'user',
  }
  const CREDENTIALS = { username: USER.username, password: ' test password ' }
  const LOGIN: LoginResult = {
    access_token: 'test-access-token',
    token_type: 'bearer',
    expires_in: 7200,
    user: { ...USER },
  }
  return { USER, CREDENTIALS, LOGIN }
}
