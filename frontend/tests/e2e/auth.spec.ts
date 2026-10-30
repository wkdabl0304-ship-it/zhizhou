/** 认证全链路：真实页面、接口与随机测试库共同验证注册、刷新和退出。 */
import { randomUUID } from 'node:crypto'
import { test, expect, login, sidebar } from '../support/playwright/fixtures'

test('注册后登录，刷新恢复身份，退出后工作区重新受保护', async ({ page }) => {
  const account = {
    username: `ui_${randomUUID().replaceAll('-', '').slice(0, 20)}`,
    password: 'e2e-password-123',
  }
  await page.goto('/')
  await expect(page).toHaveURL(/\/login/)
  await expect(page.getByRole('heading', { level: 2, name: '欢迎回来', exact: true })).toBeVisible()
  await expect(page.locator('.auth-scene p, .auth-footer, .form-eyebrow')).toHaveCount(0)
  await page.getByRole('link', { name: '创建账号', exact: true }).click()
  await expect(page.getByRole('heading', { level: 2, name: '创建账号', exact: true })).toBeVisible()
  await expect(page.getByText('3–32 位字母、数字或下划线，不区分大小写')).toBeVisible()
  await page.getByLabel('用户名', { exact: true }).fill(account.username)
  await page.getByLabel('密码', { exact: true }).fill(account.password)
  await page.getByLabel('确认密码', { exact: true }).fill(account.password)
  await page.getByRole('button', { name: '创建账号', exact: true }).click()
  await expect(page).toHaveURL(/\/login/)
  await login(page, account)
  await page.reload()
  const navigation = await sidebar(page)
  await expect(navigation.getByText(account.username, { exact: true })).toBeVisible()
  await navigation.getByRole('button', { name: '退出登录', exact: true }).click()
  await expect(page).toHaveURL(/\/login/)
  await page.goto('/')
  await expect(page).toHaveURL(/\/login/)
})

test('生产构建不提供开发预览路由', async ({ page }) => {
  await page.goto('/dev/ui')
  await expect(page.getByRole('heading', { name: '这条航线还没有开通' })).toBeVisible()
})

// 认证与工作区共用主题及独立图片，验证收起入口和跨路由恢复不丢失用户偏好。
test('认证页使用独立夜景，选择深色后登录仍保留夜色方案', async ({ page, account }, testInfo) => {
  await page.goto('/login')
  const artwork = page.locator('.river-landscape-art')
  await expect(artwork).toHaveClass(/is-loaded/)
  await expect(artwork).toHaveAttribute('src', /indigo-ink/)
  await page.screenshot({ path: testInfo.outputPath('appearance-auth-light.png'), fullPage: true })
  await page.getByRole('button', { name: '选择外观', exact: true }).click()
  await page.getByRole('menuitemradio', { name: '深色', exact: true }).click()
  await expect(artwork).toHaveAttribute('src', /indigo-night/)
  await expect(artwork).toHaveClass(/is-loaded/)
  expect(await artwork.evaluate((element) => getComputedStyle(element).filter)).toBe('none')
  await page.screenshot({ path: testInfo.outputPath('appearance-auth-dark.png'), fullPage: true })
  await login(page, account)
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await expect(artwork).toHaveAttribute('src', /indigo-night/)
})
