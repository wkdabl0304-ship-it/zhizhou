/** 聊天测试身份：通过真实认证 store 建立内存会话，网络仅使用统一契约替身。 */
import { setActivePinia, type Pinia } from 'pinia'
import type { Mock } from 'vitest'
import { useAuthStore } from '@/features/auth/store'
import { createAuthData } from '@tests/support/data/auth'
import { response } from '@tests/support/vitest/http'

/** 为当前用例登录测试账号，并从聊天请求计数中排除认证准备请求。 */
export async function authenticate(
  pinia: Pinia,
  fetchMock: Mock<typeof fetch>,
  management = false,
): Promise<void> {
  const { CREDENTIALS, LOGIN } = createAuthData()
  if (management)
    LOGIN.user.grants.push({ permission: 'model:manage', scope_type: 'global', scope_id: null })
  setActivePinia(pinia)
  fetchMock.mockResolvedValueOnce(response(LOGIN))
  await useAuthStore(pinia).login(CREDENTIALS)
  fetchMock.mockClear()
}
