/** 配置 E2E 共用资源：串行项目重置随机库配置，提供正式页面操作与另一客户端认证。 */
import { test as base, expect, type Account } from './fixtures'
import type { APIRequestContext, Page } from '@playwright/test'

/** 返回仅测试启动器提供的控制地址，缺少环境时禁止连接开发服务。 */
export function control() {
  const url = process.env.E2E_API_URL,
    token = process.env.E2E_CONTROL_TOKEN
  if (!url || !token) throw new Error('请通过 pnpm test:e2e 启动隔离服务')
  return { url, token }
}
export const test = base.extend<{ configuration: void }>({
  // 每例前后通过正式服务清理/恢复全局配置，失败也执行 finally；配置项目间由依赖图串行。
  configuration: [
    async ({ request }, use) => {
      const { url, token } = control()
      const options = { headers: { Authorization: `Bearer ${token}` } }
      expect(
        (
          await request.post(`${url}/__e2e__/model-configuration`, {
            ...options,
            data: { mode: 'empty' },
          })
        ).ok(),
      ).toBe(true)
      try {
        await use()
      } finally {
        expect(
          (
            await request.post(`${url}/__e2e__/model-configuration`, {
              ...options,
              data: { mode: 'seeded' },
            })
          ).ok(),
        ).toBe(true)
      }
    },
    { auto: true },
  ],
})

/** 从当前管理页面添加真实供应商配置，凭据始终是假值。 */
export async function provider(
  page: Page,
  name = '我的 DeepSeek',
  brand = 'deepseek',
  key = 'e2e-demo-key',
): Promise<void> {
  await page.getByRole('button', { name: '添加', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '添加供应商配置', exact: true })
  await dialog.locator('[name="provider"]').selectOption(brand)
  await dialog.getByLabel('配置名称', { exact: true }).fill(name)
  await dialog.locator('[name="api_key"]').fill(key)
  await dialog.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(dialog).not.toBeVisible()
}
/** 从所选供应商添加真实模型方案，默认参数必须经过服务器校验。 */
export async function model(page: Page, name = '日常问答'): Promise<void> {
  await page.getByRole('button', { name: '添加模型方案', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '添加模型方案', exact: true })
  await dialog.getByLabel('方案名称', { exact: true }).fill(name)
  await dialog.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(dialog).not.toBeVisible()
}
/** 经正式登录接口取得当前测试账号令牌，供另一个客户端模拟共享配置修改。 */
export async function headers(request: APIRequestContext, account: Account) {
  const response = await request.post(`${control().url}/api/auth/login`, { data: account })
  expect(response.ok()).toBe(true)
  const result = await response.json()
  expect(result.code).toBe(0)
  return { Authorization: `Bearer ${result.data.access_token as string}` }
}
