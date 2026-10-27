/** 浏览器导航：真实删除、主题持久化与响应式模态焦点，不依赖截图像素比较。 */
import {
  test,
  expect,
  login,
  sidebar,
  closeSidebar,
  send,
  finished,
} from '../support/playwright/fixtures'

// 同一侧栏在两个业务页面间保持尺寸、会话和折叠状态，手机继续使用原导航抽屉。
test('进入模型管理保留侧栏，选中入口并能从会话目录返回聊天', async ({ page, account }) => {
  await login(page, account)
  await send(page, '管理页导航回归')
  await finished(page)
  const narrow = page.viewportSize()!.width <= 760
  let navigation = await sidebar(page)
  const initialBox = await navigation.boundingBox()
  const desktopNode = narrow ? null : await navigation.elementHandle()
  if (!narrow) await navigation.getByRole('button', { name: '收起侧栏', exact: true }).click()
  const foldedBox = await navigation.boundingBox()
  await navigation.getByRole('link', { name: '模型管理', exact: true }).click()
  await expect(page.getByRole('heading', { level: 1, name: '模型管理', exact: true })).toBeVisible()
  if (narrow) {
    await expect(navigation).not.toBeVisible()
    await page.getByRole('button', { name: '打开侧栏', exact: true }).click()
    navigation = page.getByRole('dialog', { name: '会话导航', exact: true })
  } else {
    expect(await desktopNode!.evaluate((element) => element.isConnected)).toBe(true)
    expect((await navigation.boundingBox())!.width).toBe(foldedBox!.width)
    await expect(navigation.getByRole('button', { name: '展开侧栏', exact: true })).toBeVisible()
    await navigation.getByRole('button', { name: '展开侧栏', exact: true }).click()
    expect((await navigation.boundingBox())!.width).toBe(initialBox!.width)
  }
  await expect(navigation.getByRole('link', { name: '模型管理', exact: true })).toHaveAttribute(
    'aria-current',
    'page',
  )
  await expect(
    navigation.getByRole('button', { name: '管理页导航回归', exact: true }),
  ).toBeVisible()
  await navigation.getByRole('button', { name: '管理页导航回归', exact: true }).click()
  await expect(
    page.getByRole('heading', { level: 1, name: '管理页导航回归', exact: true }),
  ).toBeVisible()
  await expect(page.getByRole('textbox', { name: '消息内容' })).toBeVisible()
  await expect(page.getByRole('article')).toHaveCount(2)
})

// 子页面卸载不能丢失 store 中的生成任务；使用门控保证导航发生在真实 SSE 的两段回复之间。
test('生成期间进入模型管理再返回，原回复继续完成且刷新后可读', async ({
  page,
  account,
  modelGate,
}) => {
  await login(page, account)
  const gate = await modelGate()
  await send(page, gate.prompt)
  await expect(page.getByRole('article', { name: '知舟的回复', exact: true })).toContainText(
    '已收到部分回答',
  )
  await (await sidebar(page)).getByRole('link', { name: '模型管理', exact: true }).click()
  await expect(page.getByRole('heading', { name: '模型管理', exact: true })).toBeVisible()
  expect(await gate.closed()).toBe(false)
  await page.goBack()
  await expect(page.getByRole('textbox', { name: '消息内容' })).toBeVisible()
  await expect(page.getByRole('article', { name: '知舟的回复', exact: true })).toContainText(
    '已收到部分回答',
  )
  await gate.release()
  await expect(await finished(page)).toContainText('已收到部分回答，现在完成。')
  await page.reload()
  await (
    await sidebar(page)
  )
    .getByRole('button', { name: gate.prompt.slice(0, 24), exact: true })
    .click()
  await expect(await finished(page)).toContainText('已收到部分回答，现在完成。')
})

test('删除必须确认，取消保留数据，确认后刷新目录仍不显示', async ({ page, account }) => {
  await login(page, account)
  await send(page, '待删除会话')
  await finished(page)
  let navigation = await sidebar(page)
  await navigation.getByRole('button', { name: '删除会话：待删除会话', exact: true }).click()
  await navigation.getByRole('button', { name: '取消', exact: true }).click()
  await expect(navigation.getByRole('button', { name: '待删除会话', exact: true })).toBeVisible()
  await navigation.getByRole('button', { name: '删除会话：待删除会话', exact: true }).click()
  await navigation.getByRole('button', { name: '确认删除', exact: true }).click()
  await expect(navigation.getByRole('button', { name: '待删除会话', exact: true })).toHaveCount(0)
  await closeSidebar(page)
  await expect(page.getByRole('article')).toHaveCount(0)
  await expect(page.getByRole('heading', { name: '此刻，思考启程', exact: true })).toBeVisible()
  await page.reload()
  navigation = await sidebar(page)
  await expect(navigation).toContainText('还没有对话')
})

test('主题切换后刷新保持选择，Portal 菜单同步当前主题', async ({ page, account }) => {
  await login(page, account)
  const navigation = await sidebar(page)
  await navigation.getByRole('button', { name: /外观.*浅色/ }).click()
  await page.getByRole('menuitemradio', { name: '深色', exact: true }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await closeSidebar(page)
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await (await sidebar(page)).getByRole('button', { name: /外观.*深色/ }).click()
  await expect(page.getByRole('menuitemradio', { name: '深色', exact: true })).toHaveAttribute(
    'aria-checked',
    'true',
  )
})

test('抽屉约束焦点，Esc 恢复入口，切回桌面恢复页面交互', async ({ page, account }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await login(page, account)
  const trigger = page.getByRole('button', { name: '打开侧栏', exact: true })
  await trigger.focus()
  await page.keyboard.press('Enter')
  const dialog = page.getByRole('dialog', { name: '会话导航', exact: true })
  await expect(dialog).toBeVisible()
  await page.keyboard.press('Tab')
  await expect
    .poll(() => dialog.evaluate((element) => element.contains(document.activeElement)))
    .toBe(true)
  await page.keyboard.press('Escape')
  await expect(dialog).not.toBeVisible()
  await expect(trigger).toBeFocused()
  // 用真实长回复建立可滚动区域，切回桌面后通过滚轮验证滚动已恢复。
  await send(
    page,
    Array.from({ length: 50 }, (_, index) => `第${index + 1}段：验证滚动恢复。`).join('\n\n'),
  )
  await finished(page)
  await trigger.click()
  await expect(dialog).toBeVisible()
  await page.setViewportSize({ width: 1440, height: 900 })
  await expect(dialog).not.toBeVisible()
  await expect(page.getByRole('heading', { level: 1, name: /^第1段：验证滚动恢复/ })).toBeFocused()
  const history = page.getByRole('region', { name: '对话内容', exact: true })
  await expect.poll(() => history.evaluate((element) => element.scrollTop)).toBeGreaterThan(0)
  const previousTop = await history.evaluate((element) => element.scrollTop)
  await history.hover()
  await page.mouse.wheel(0, -600)
  await expect
    .poll(() => history.evaluate((element) => element.scrollTop))
    .toBeLessThan(previousTop)
  const input = page.getByRole('textbox', { name: '消息内容' })
  await input.fill('恢复交互')
  await expect(input).toHaveValue('恢复交互')
})
