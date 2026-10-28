/** 表单控件浏览器支撑：通过真实点击选择 Portal 选项，不操作代理表单值。 */
import { expect, type Locator, type Page } from '@playwright/test'

/** 展开指定选择器并按业务值选择，等待菜单关闭后继续表单流程。 */
export async function selectOption(page: Page, trigger: Locator, value: string): Promise<void> {
  await trigger.click()
  const option = page.locator(`[role="option"][data-value=${JSON.stringify(value)}]`)
  await expect(option).toBeVisible()
  await option.click()
  await expect(trigger).toHaveAttribute('aria-expanded', 'false')
}
