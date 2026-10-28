/** 开发控件页浏览器验收：键盘选择、错误与禁用、标签点击、明暗主题和窄屏不溢出。 */
import { expect, test } from '@playwright/test'

test('共享控件支持完整表单操作、键盘取消与明暗主题', async ({ page }, testInfo) => {
  const errors: string[] = []
  // 开发预览的任何未捕获浏览器异常都使验收失败。
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/dev/ui')
  const controls = page.getByRole('region', { name: '基础表单控件', exact: true })
  await expect(controls).toBeVisible()
  const input = page.getByRole('textbox', { name: '示例用户名', exact: true })
  await input.fill('lin_zhou')
  expect(await input.evaluate((element) => getComputedStyle(element).outlineStyle)).toBe('none')
  const trigger = page.getByRole('combobox', { name: '示例账号状态', exact: true })
  await trigger.focus()
  await page.keyboard.press('ArrowDown')
  await expect(page.getByRole('option', { name: '全部状态', exact: true })).toBeFocused()
  await page.keyboard.press('End')
  await expect(page.getByRole('option', { name: '已停用', exact: true })).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(trigger).toContainText('已停用')
  await trigger.press('ArrowDown')
  await expect(page.getByRole('option', { name: '已停用', exact: true })).toBeFocused()
  await page.keyboard.press('Home')
  await expect(page.getByRole('option', { name: '全部状态', exact: true })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(trigger).toContainText('已停用')
  await expect(trigger).toBeFocused()
  await page.getByText('仅无部门', { exact: true }).click()
  const checkbox = page.getByRole('checkbox', { name: '仅无部门', exact: true })
  await expect(checkbox).toBeChecked()
  await checkbox.hover()
  await expect(checkbox).toHaveCSS('cursor', 'pointer')
  await page.getByRole('button', { name: '查看表单结果', exact: true }).click()
  await expect(
    page.getByRole('status').filter({ hasText: 'lin_zhou · 已停用 · 仅无部门' }),
  ).toBeVisible()
  await expect(
    page.getByRole('checkbox', { name: '已选中 · 不可修改', exact: true }),
  ).toBeDisabled()
  await controls.screenshot({ path: testInfo.outputPath('controls-light.png') })
  await page.getByRole('button', { name: '外观 浅色', exact: true }).click()
  await page.getByRole('menuitemradio', { name: '深色', exact: true }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await controls.screenshot({ path: testInfo.outputPath('controls-dark.png') })
  await trigger.click()
  await expect(page.getByRole('option', { name: '已停用', exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('controls-menu-dark.png') })
  expect(
    await page.locator('body').evaluate((element) => element.scrollWidth <= window.innerWidth),
  ).toBe(true)
  expect(errors).toEqual([])
})
