/** 权限 E2E 支撑：注册后通过测试运维通道授予超管，业务操作继续使用正式接口。 */
import { test as base, expect, createAccount, type Account } from './fixtures'
import type { APIRequestContext } from '@playwright/test'

/** 取得本次隔离启动器提供的后端地址，拒绝误连开发环境。 */
export function apiUrl(): string {
  if (!process.env.E2E_API_URL) throw new Error('请使用 pnpm test:e2e 启动隔离服务')
  return process.env.E2E_API_URL
}

/** 为已注册测试账号授予全局管理角色，不修改全局模型配置。 */
export async function grantAdmin(request: APIRequestContext, account: Account): Promise<void> {
  const token = process.env.E2E_CONTROL_TOKEN
  if (!token) throw new Error('E2E 缺少运维控制令牌')
  const result = await request.post(`${apiUrl()}/__e2e__/super-admin`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { username: account.username },
  })
  expect(result.ok()).toBe(true)
}

/** 使用正式登录接口获取另一客户端的身份，仅供跨账号生命周期断言及数据准备。 */
export async function identity(request: APIRequestContext, account: Account) {
  const result = await request.post(`${apiUrl()}/api/auth/login`, { data: account })
  expect(result.ok()).toBe(true)
  const body = await result.json()
  return {
    user: body.data.user as { id: string },
    headers: { Authorization: `Bearer ${body.data.access_token}` },
  }
}

export const test = base.extend({
  // 每例使用独立管理员，避免撤权或停用操作影响并行运行的其他账号。
  account: async ({ request }, use) => {
    const account = await createAccount(request)
    await grantAdmin(request, account)
    await use(account)
  },
})
