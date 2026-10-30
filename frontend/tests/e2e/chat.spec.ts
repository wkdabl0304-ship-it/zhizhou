/** 聊天全链路：真实 SSE、业务历史与 checkpoint，只有模型供应商被本地替身替换。 */
import {
  accountAppearance,
  accountMenu,
  test,
  expect,
  login,
  sidebar,
  send,
  finished,
  closeSidebar,
  createAccount,
} from '../support/playwright/fixtures'
import { openRename, openDelete } from '../support/playwright/conversations'

test('首轮与续聊完成后，刷新仍可打开持久化历史', async ({ page, account }) => {
  await login(page, account)
  await send(page, '测试持久化')
  await expect(await finished(page)).toContainText('测试持久化')
  await send(page, '继续回答')
  await expect(await finished(page)).toContainText('测试持久化|继续回答')
  await page.reload()
  await (await sidebar(page)).getByRole('button', { name: '测试持久化', exact: true }).click()
  await expect(page.getByRole('article', { name: '你的消息', exact: true })).toHaveCount(2)
  await expect(await finished(page)).toContainText('测试持久化|继续回答')
})

// 从侧栏弹窗保存真实标题，继续验证刷新、续聊和标题优先级。
test('手动修改标题后，刷新和继续聊天都保留新标题', async ({ page, account }, testInfo) => {
  await login(page, account)
  await send(page, '标题持久化验收')
  await finished(page)
  await page.getByRole('textbox', { name: '消息内容' }).fill('改名不清空消息草稿')
  const navigation = await sidebar(page)
  await navigation
    .getByRole('button', { name: '修改会话标题：标题持久化验收', exact: true })
    .click()
  const dialog = page.getByRole('dialog', { name: '修改会话标题', exact: true })
  const input = dialog.getByRole('textbox', { name: '会话标题', exact: true })
  await expect(input).toBeFocused()
  await input.fill('  手动保存的   会话标题  ')
  await page.screenshot({
    path: testInfo.outputPath('conversation-title-dialog.png'),
    fullPage: true,
  })
  const saved = page.waitForResponse(
    (response) => response.url().endsWith('/title') && response.request().method() === 'PATCH',
  )
  await input.press('Enter')
  const renamed = await saved
  expect(renamed.ok()).toBe(true)
  expect(await renamed.json()).toMatchObject({ code: 0, data: { title: '手动保存的 会话标题' } })
  await expect(
    navigation.getByRole('button', { name: '修改会话标题：手动保存的 会话标题', exact: true }),
  ).toBeFocused()
  await page.screenshot({
    path: testInfo.outputPath('conversation-title-saved.png'),
    fullPage: true,
  })
  await closeSidebar(page)
  await expect(
    page.getByRole('heading', { level: 1, name: '手动保存的 会话标题', exact: true }),
  ).toBeVisible()
  await expect(page.getByRole('textbox', { name: '消息内容' })).toHaveValue('改名不清空消息草稿')
  await page.reload()
  await (
    await sidebar(page)
  )
    .getByRole('button', { name: '手动保存的 会话标题', exact: true })
    .click()
  await closeSidebar(page)
  await send(page, '改名后继续')
  await expect(await finished(page)).toContainText('标题持久化验收|改名后继续')
  await page.reload()
  await expect(
    (await sidebar(page)).getByRole('button', { name: '手动保存的 会话标题', exact: true }),
  ).toBeVisible()
})

test('部分回答先显示，模型释放后才交付最终回答', async ({ page, account, modelGate }) => {
  const gate = await modelGate()
  await login(page, account)
  await send(page, gate.prompt)
  const answer = page.getByRole('article', { name: '知舟的回复', exact: true })
  await expect(answer).toContainText('已收到部分回答')
  await expect(answer.getByRole('button', { name: '复制回复', exact: true })).toHaveCount(0)
  // 正式标题在 done 前保存，客户端随后读取同一会话元数据，无需刷新整个页面。
  const titleRead = page.waitForResponse(
    (response) =>
      /\/api\/conversations\/[^/?]+\?limit=20$/.test(response.url()) &&
      response.request().method() === 'GET',
  )
  await gate.release()
  await expect(await finished(page)).toContainText('已收到部分回答，现在完成。')
  const title = (await (await titleRead).json()).data.conversation.title
  await expect(page.getByRole('heading', { level: 1, name: title, exact: true })).toBeVisible()
})

// 同一弹窗承接按钮和双击入口，编辑与删除都不借助侧栏内嵌确认区域。
test('双击侧栏及页头可弹窗改名，删除弹窗取消和失败重试保持会话', async ({
  page,
  account,
}, testInfo) => {
  await login(page, account)
  await send(page, '双击改名验收')
  await finished(page)
  await page.getByRole('textbox', { name: '消息内容' }).fill('双击不丢草稿')
  const dialog = await openRename(page, '双击改名验收', true)
  await dialog.getByRole('textbox', { name: '会话标题', exact: true }).press('Escape')
  await expect(dialog).not.toBeVisible()
  await closeSidebar(page)
  await expect(page.getByRole('textbox', { name: '消息内容' })).toHaveValue('双击不丢草稿')
  await page.getByRole('heading', { level: 1, name: '双击改名验收', exact: true }).dblclick()
  await expect(dialog).toBeVisible()
  await dialog.getByRole('textbox', { name: '会话标题', exact: true }).fill('弹窗新标题')
  await dialog.getByRole('button', { name: '保存标题', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  await expect(
    page.getByRole('heading', { level: 1, name: '弹窗新标题', exact: true }),
  ).toBeVisible()
  await expect(page.getByRole('textbox', { name: '消息内容' })).toHaveValue('双击不丢草稿')
  const deletion = await openDelete(page, '弹窗新标题')
  await page.screenshot({
    path: testInfo.outputPath('conversation-delete-dialog.png'),
    fullPage: true,
  })
  await page.keyboard.press('Escape')
  await expect(deletion).not.toBeVisible()
  await openDelete(page, '弹窗新标题')
  await page.route('**/api/conversations/*', (route) =>
    route.request().method() === 'DELETE'
      ? route.fulfill({
          status: 503,
          contentType: 'application/json',
          body: JSON.stringify({ code: 50300, message: '暂时无法删除', data: null }),
        })
      : route.continue(),
  )
  await deletion.getByRole('button', { name: '确认删除', exact: true }).click()
  await expect(deletion.getByRole('alert')).toContainText('暂时无法删除')
  await expect(deletion).toBeVisible()
  await page.unroute('**/api/conversations/*')
  await deletion.getByRole('button', { name: '确认删除', exact: true }).click()
  await expect(deletion).not.toBeVisible()
  await expect(
    (await sidebar(page)).getByRole('button', { name: '弹窗新标题', exact: true }),
  ).toHaveCount(0)
})

// 真实生成不限制改名；只在故障注入的一次请求替换 HTTP，其余步骤使用真实后端和随机库。
test('生成中改名支持校验、取消和失败重试，自动标题不会覆盖手动标题', async ({
  page,
  account,
  modelGate,
}, testInfo) => {
  const gate = await modelGate()
  await login(page, account)
  await accountAppearance(page)
  await page.getByRole('menuitemradio', { name: '深色', exact: true }).click()
  await closeSidebar(page)
  await send(page, gate.prompt)
  await expect(page.getByRole('article', { name: '知舟的回复', exact: true })).toContainText(
    '已收到部分回答',
  )
  const navigation = await sidebar(page)
  const oldTitle = gate.prompt.slice(0, 24)
  const edit = navigation.getByRole('button', { name: `修改会话标题：${oldTitle}`, exact: true })
  await expect(edit).toBeEnabled()
  await edit.click()
  const dialog = page.getByRole('dialog', { name: '修改会话标题', exact: true })
  const input = dialog.getByRole('textbox', { name: '会话标题', exact: true })
  await input.fill('   ')
  await input.press('Enter')
  await expect(dialog.getByRole('alert')).toContainText('请输入会话标题')
  await input.fill('取消后的草稿')
  await input.press('Escape')
  await expect(page.getByRole('dialog', { name: '修改会话标题', exact: true })).toHaveCount(0)
  await expect(edit).toBeFocused()
  await edit.click()
  await expect(input).toHaveValue(oldTitle)
  await input.fill('生成中手动标题')
  await page.route('**/api/conversations/*/title', (route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ code: 50300, message: '暂时无法保存标题', data: null }),
    }),
  )
  await input.press('Enter')
  await expect(dialog.getByRole('alert')).toContainText('暂时无法保存标题')
  await expect(input).toHaveValue('生成中手动标题')
  await page.screenshot({
    path: testInfo.outputPath('conversation-title-error.png'),
    fullPage: true,
  })
  await page.unroute('**/api/conversations/*/title')
  await input.press('Enter')
  await expect(dialog).not.toBeVisible()
  await expect(
    navigation.getByRole('button', { name: '生成中手动标题', exact: true }),
  ).toBeVisible()
  await closeSidebar(page)
  await gate.release()
  await finished(page)
  await expect(
    page.getByRole('heading', { level: 1, name: '生成中手动标题', exact: true }),
  ).toBeVisible()
  await page.reload()
  await expect(
    (await sidebar(page)).getByRole('button', { name: '生成中手动标题', exact: true }),
  ).toBeVisible()
})

test('真实工具执行显示公开过程，模型失败后保留部分内容', async ({ page, account, modelGate }) => {
  await login(page, account)
  await send(page, '天气')
  const weather = await finished(page)
  await expect(weather).toContainText('上海')
  await weather.getByRole('button', { name: /已完成.*项操作/ }).click()
  await expect(weather.getByRole('region', { name: '执行过程' })).toContainText('get_weather')
  await page.getByRole('button', { name: '新建对话', exact: true }).last().click()
  const gate = await modelGate('fail')
  await send(page, gate.prompt)
  const answer = page.getByRole('article', { name: '知舟的回复', exact: true })
  await expect(answer).toContainText('已收到部分回答')
  await gate.release()
  await expect(answer.getByRole('alert')).toContainText('回复未完成')
  await expect(answer).toContainText('已收到部分回答')
})

test('切换会话保持生成归属，退出取消模型，另一账号不读取旧数据', async ({
  page,
  account,
  request,
  modelGate,
}) => {
  await login(page, account)
  const gate = await modelGate()
  await send(page, gate.prompt)
  await expect(page.getByRole('article', { name: '知舟的回复', exact: true })).toContainText(
    '已收到部分回答',
  )
  await page.getByRole('button', { name: '新建对话', exact: true }).last().click()
  await expect(page.getByRole('article', { name: '知舟的回复', exact: true })).toHaveCount(0)
  await send(page, '另一段对话')
  await expect(await finished(page)).toContainText('另一段对话')
  const navigation = await sidebar(page)
  await navigation.getByRole('button', { name: gate.prompt.slice(0, 24), exact: true }).click()
  await expect(page.getByRole('article', { name: '知舟的回复', exact: true })).toContainText(
    '已收到部分回答',
  )
  await (await accountMenu(page)).getByRole('menuitem', { name: '退出登录', exact: true }).click()
  await expect(page).toHaveURL(/\/login/)
  await expect.poll(gate.closed).toBe(true)
  const other = await createAccount(request)
  await login(page, other)
  await expect(await sidebar(page)).toContainText('暂无对话')
  await closeSidebar(page)
  await expect(page.getByRole('article')).toHaveCount(0)
})

// 第二页面没有本地 SSE，必须通过受限轮询自动恢复最终历史，无需任何刷新按钮。
test('远端会话生成结束自动同步，新首页无示例且输入区尺寸适中', async ({
  page,
  account,
  modelGate,
}, testInfo) => {
  await login(page, account)
  await expect(page.locator('.suggestion')).toHaveCount(0)
  await expect(page.getByText('一起探索，慢慢理清', { exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '设置推理强度', exact: true })).toBeVisible()
  const composer = page.getByRole('form', { name: '发送消息', exact: true })
  const composerBox = await composer.boundingBox()
  expect(composerBox!.height).toBeGreaterThan(120)
  expect(composerBox!.height).toBeLessThan(170)
  expect(composerBox!.width).toBeLessThanOrEqual(860)
  await page.screenshot({ path: testInfo.outputPath('expanded-composer.png'), fullPage: true })
  const gate = await modelGate()
  await send(page, gate.prompt)
  await expect(page.getByRole('article', { name: '知舟的回复', exact: true })).toContainText(
    '已收到部分回答',
  )
  const other = await page.context().newPage()
  try {
    await login(other, account)
    await (
      await sidebar(other)
    )
      .getByRole('button', { name: gate.prompt.slice(0, 24), exact: true })
      .click()
    await closeSidebar(other)
    await expect(
      other.getByRole('status').filter({ hasText: '此会话正在其他页面生成' }),
    ).toBeVisible()
    await expect(other.getByRole('button', { name: /刷新/ })).toHaveCount(0)
    await gate.release()
    await expect(await finished(other)).toContainText('已收到部分回答，现在完成。')
    await expect(other.getByRole('textbox', { name: '消息内容', exact: true })).toBeEnabled()
  } finally {
    await other.close()
  }
})
