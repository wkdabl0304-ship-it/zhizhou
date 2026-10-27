/** E2E fixture：每例独立真实账号和浏览器上下文，仅通过测试通道控制模型边界。 */
import { randomUUID } from 'node:crypto'
import {
  test as base,
  expect,
  type APIRequestContext,
  type Locator,
  type Page,
} from '@playwright/test'

/** 独立测试账号的明文凭据，仅在随机临时库和本例内使用。 */
export interface Account {
  username: string
  password: string
}

/** 已登记的模型门控场景，方法通过测试专用接口显式推进或观察清理。 */
export interface ModelGate {
  prompt: string
  release: () => Promise<void>
  closed: () => Promise<boolean>
}

/** 读取启动器提供的环境值，缺失时阻止误连开发服务。 */
function required(name: string): string {
  const value = process.env[name]
  if (!value) throw new Error(`E2E 缺少 ${name}，请运行 pnpm test:e2e`)
  return value
}

/** 通过真实后端创建唯一普通账号，不直接写数据库。 */
export async function createAccount(request: APIRequestContext): Promise<Account> {
  const account = {
    username: `e2e_${randomUUID().replaceAll('-', '').slice(0, 20)}`,
    password: 'e2e-password-123',
  }
  const result = await request.post(`${required('E2E_API_URL')}/api/auth/register`, {
    data: account,
  })
  expect(result.ok()).toBe(true)
  expect(await result.json()).toMatchObject({ code: 0, data: { username: account.username } })
  return account
}

export const test = base.extend<{
  account: Account
  modelGate: (kind?: 'hold' | 'fail') => Promise<ModelGate>
}>({
  // Playwright 为每例创建上下文；这里额外将未处理浏览器异常作为用例失败。
  page: async ({ page }, use) => {
    const errors: string[] = []
    page.on('pageerror', (error) => errors.push(error.message))
    await use(page)
    expect(errors).toEqual([])
  },
  // 账号通过正式注册接口准备；注册流程本身另有完整 UI 用例。
  account: async ({ request }, use) => {
    await use(await createAccount(request))
  },
  // 每个场景有独立门控，收尾释放未完成场景，避免失败用例拖住服务器退出。
  modelGate: async ({ request }, use) => {
    const gates: ModelGate[] = []
    const headers = { Authorization: `Bearer ${required('E2E_CONTROL_TOKEN')}` }
    const endpoint = `${required('E2E_API_URL')}/__e2e__/scenarios`
    await use(async (kind = 'hold') => {
      const response = await request.post(endpoint, { headers, data: { kind } })
      expect(response.ok()).toBe(true)
      const { prompt } = (await response.json()) as { prompt: string }
      const gate: ModelGate = {
        prompt,
        // 控制响应也必须成功，不能把门控未释放误判为页面等待失败。
        release: async () => {
          expect((await request.post(`${endpoint}/${prompt}/release`, { headers })).ok()).toBe(true)
        },
        // 读取服务端模型 finally 状态，确认取消沿真实 HTTP 链路传播。
        closed: async () => {
          const state = await request.get(`${endpoint}/${prompt}`, { headers })
          expect(state.ok()).toBe(true)
          return ((await state.json()) as { closed: boolean }).closed
        },
      }
      gates.push(gate)
      return gate
    })
    for (const gate of gates) await gate.release()
  },
})

export { expect }

/** 使用真实登录页面建立身份，让认证表单、路由守卫和 /me 都参与验证。 */
export async function login(page: Page, account: Account): Promise<void> {
  await page.goto('/login')
  await page.getByLabel('用户名', { exact: true }).fill(account.username)
  await page.getByLabel('密码', { exact: true }).fill(account.password)
  await page.getByRole('button', { name: '登录知舟', exact: true }).click()
  await expect(page.getByRole('textbox', { name: '消息内容' })).toBeVisible()
}

/** 返回当前可操作的导航，窄屏时通过用户入口展开抽屉。 */
export async function sidebar(page: Page): Promise<Locator> {
  const dialog = page.getByRole('dialog', { name: '会话导航', exact: true })
  if (await dialog.isVisible()) return dialog
  // 等待共用工作区挂载，兼容没有聊天输入框的模型管理页。
  await expect(page.locator('.chat-shell')).toBeVisible()
  const trigger = page.getByRole('button', { name: '打开侧栏', exact: true })
  if (await trigger.isVisible()) {
    await trigger.click()
    await expect(dialog).toBeVisible()
    return dialog
  }
  return page.getByRole('complementary', { name: '知舟导航', exact: true })
}

/** 关闭当前窄屏导航，防止模态层遮挡正文或输入区。 */
export async function closeSidebar(page: Page): Promise<void> {
  // 等待用户已经触发的选中和子弹窗关闭完成，不用 Esc 抢先取消双击判定中的单击。
  await expect(page.locator('.conversation-item[aria-busy="true"]')).toHaveCount(0)
  await expect(page.locator('.ui-modal[data-state="open"]')).toHaveCount(0)
  const dialog = page.getByRole('dialog', { name: '会话导航', exact: true })
  if (await page.locator('.ui-drawer[data-state="open"]').isVisible()) {
    await expect(dialog).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(dialog).not.toBeVisible()
  }
}

/** 通过实际输入与发送按钮开启一轮请求，不注入前端 store 或替换业务接口。 */
export async function send(page: Page, message: string): Promise<void> {
  await expect(page.locator('.conversation-item[aria-busy="true"]')).toHaveCount(0)
  await page.getByRole('textbox', { name: '消息内容' }).fill(message)
  await page.getByRole('button', { name: '发送消息', exact: true }).click()
}

/** 等待最终回答的公开完成状态，避免仅凭收到部分文字就刷新或删除会话。 */
export async function finished(page: Page): Promise<Locator> {
  const answer = page.getByRole('article', { name: '知舟的回复', exact: true }).last()
  await expect(answer.getByRole('button', { name: '复制回复', exact: true })).toBeVisible()
  return answer
}
