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

/** 进入指定品牌的居中弹窗，已打开同品牌时直接复用。 */
export async function openProvider(page: Page, brand = 'deepseek'): Promise<void> {
  const names: Record<string, string> = {
    openai: 'OpenAI',
    anthropic: 'Anthropic',
    deepseek: 'DeepSeek',
    bailian: '阿里云百炼',
  }
  const title = names[brand]!
  if (await page.getByRole('dialog', { name: title, exact: true }).isVisible()) return
  await closeProvider(page)
  await page.getByRole('button', { name: '配置 ' + title, exact: true }).click()
  await expect(page.getByRole('dialog', { name: title, exact: true })).toBeVisible()
}

/** 关闭供应商弹窗，让页面摘要和工作区导航恢复可操作。 */
export async function closeProvider(page: Page): Promise<void> {
  const dialog = page.locator('.config-modal--wide')
  if (await dialog.isVisible()) {
    await dialog.getByRole('button', { name: '关闭', exact: true }).click()
    await expect(dialog).not.toBeVisible()
  }
}

/** 从品牌卡片保存真实连接，凭据始终是假值。 */
export async function provider(
  page: Page,
  name = '我的 DeepSeek',
  brand = 'deepseek',
  key = 'e2e-demo-key',
): Promise<void> {
  await openProvider(page, brand)
  const editor = page.getByRole('dialog', { name: '添加供应商配置', exact: true })
  if (!(await editor.isVisible()))
    await page.getByRole('button', { name: '添加连接', exact: true }).click()
  await editor.getByLabel('配置名称', { exact: true }).fill(name)
  await editor.locator('[name="api_key"]').fill(key)
  await editor.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(editor).not.toBeVisible()
}

/** 开启一个未保存目录模型；可选的测试名称通过正式高级设置保存。 */
export async function model(page: Page, name = '日常问答', catalogName?: string): Promise<void> {
  const row = catalogName
    ? page.getByRole('article', { name: '模型方案：' + catalogName, exact: true })
    : page
        .getByRole('region', { name: '关联模型方案', exact: true })
        .getByRole('article')
        .filter({ has: page.getByRole('switch', { checked: false }) })
        .first()
  const toggle = row.getByRole('switch')
  const rowLabel = await row.getAttribute('aria-label')
  await toggle.click()
  // 开启后该行不再匹配“关闭”的过滤条件，后续按稳定的模型名称重新定位。
  const saved = page.getByRole('article', { name: rowLabel!, exact: true })
  await expect(saved.getByRole('switch')).toBeChecked()
  await saved.getByRole('button', { name: '高级设置', exact: true }).click()
  const editor = page.getByRole('dialog', { name: '编辑模型方案', exact: true })
  await editor.locator('[name="name"]').fill(name)
  await editor.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(editor).not.toBeVisible()
}

/** 经正式登录接口取得当前测试账号令牌，供另一个客户端模拟共享配置修改。 */
export async function headers(request: APIRequestContext, account: Account) {
  const response = await request.post(`${control().url}/api/auth/login`, { data: account })
  expect(response.ok()).toBe(true)
  const result = await response.json()
  expect(result.code).toBe(0)
  return { Authorization: `Bearer ${result.data.access_token as string}` }
}

/** 使用浏览器后退返回先前聊天，验证精简管理页后仍能保留会话与未发送草稿。 */
export async function returnToChat(page: Page): Promise<void> {
  await page.goBack()
  await expect(page.getByRole('textbox', { name: '消息内容', exact: true })).toBeVisible()
}
