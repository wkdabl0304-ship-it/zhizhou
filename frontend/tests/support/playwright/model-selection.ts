/** 聊天模型下拉 E2E 操作：从输入区真实入口选择、刷新和关闭浮层。 */
import { expect, type Page } from '@playwright/test'

/** 展开发送按钮左侧的模型菜单，已打开时保持原状态。 */
export async function openPicker(page: Page): Promise<void> {
  const trigger = page.getByRole('button', { name: '选择聊天模型', exact: true })
  if ((await trigger.getAttribute('aria-expanded')) !== 'true') await trigger.click()
  await expect(page.getByRole('dialog', { name: '选择聊天模型', exact: true })).toBeVisible()
}

/** 通过 Esc 关闭模型菜单并恢复输入区入口焦点。 */
export async function closePicker(page: Page): Promise<void> {
  const menu = page.getByRole('dialog', { name: '选择聊天模型', exact: true })
  if (await menu.isVisible()) {
    await page.keyboard.press('Escape')
    await expect(menu).not.toBeVisible()
  }
}

/** 点击模型选项后等待保存并自动收起，不绕过会话版本校验。 */
export async function chooseModel(page: Page, name: string): Promise<void> {
  await openPicker(page)
  await page.getByRole('option', { name: new RegExp('^' + name) }).click()
  await expect(page.getByRole('dialog', { name: '选择聊天模型', exact: true })).not.toBeVisible()
  await expect(page.getByRole('button', { name: '选择聊天模型', exact: true })).toContainText(name)
}

/** 重新打开菜单以自动同步允许范围，不提供手动刷新按钮。 */
export async function refreshModels(page: Page): Promise<void> {
  await closePicker(page)
  const reading = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/model-config/options') && response.request().method() === 'GET',
  )
  await openPicker(page)
  await (await reading).finished()
  await closePicker(page)
}

/** 打开独立的思考强度浮层，模型菜单保持关闭。 */
export async function openReasoning(page: Page): Promise<void> {
  await closePicker(page)
  const trigger = page.getByRole('button', { name: '设置推理强度', exact: true })
  if ((await trigger.getAttribute('aria-expanded')) !== 'true') await trigger.click()
  await expect(page.getByRole('dialog', { name: '设置推理强度', exact: true })).toBeVisible()
}

/** 取消未提交的强度输入并恢复思考入口焦点。 */
export async function closeReasoning(page: Page): Promise<void> {
  const menu = page.getByRole('dialog', { name: '设置推理强度', exact: true })
  if (await menu.isVisible()) {
    await page.keyboard.press('Escape')
    await expect(menu).not.toBeVisible()
  }
}
