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
  await page.getByRole('link', { name: '创建账号', exact: true }).click()
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
