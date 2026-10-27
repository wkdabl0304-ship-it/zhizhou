/** 会话操作辅助：通过真实按钮或双击进入弹窗，Portal 内容按全局可访问名称定位。 */
import { expect, type Page } from '@playwright/test'
import { sidebar } from './fixtures'

/** 打开指定会话的改名弹窗，默认使用铅笔按钮，可选双击标题。 */
export async function openRename(page: Page, title: string, doubleClick = false) {
  const navigation = await sidebar(page)
  if (doubleClick) await navigation.getByRole('button', { name: title, exact: true }).dblclick()
  else await navigation.getByRole('button', { name: `修改会话标题：${title}`, exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '修改会话标题', exact: true })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('textbox', { name: '会话标题', exact: true })).toBeFocused()
  return dialog
}

/** 从侧栏删除按钮打开确认弹窗，默认焦点位于取消，避免误触危险操作。 */
export async function openDelete(page: Page, title: string) {
  await (
    await sidebar(page)
  )
    .getByRole('button', { name: `删除会话：${title}`, exact: true })
    .click()
  const dialog = page.getByRole('dialog', { name: '删除会话？', exact: true })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('button', { name: '取消', exact: true })).toBeFocused()
  return dialog
}
