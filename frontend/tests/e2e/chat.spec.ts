/** 聊天全链路：真实 SSE、业务历史与 checkpoint，只有模型供应商被本地替身替换。 */
import {
  test,
  expect,
  login,
  sidebar,
  send,
  finished,
  closeSidebar,
  createAccount,
} from '../support/playwright/fixtures'

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

test('部分回答先显示，模型释放后才交付最终回答', async ({ page, account, modelGate }) => {
  const gate = await modelGate()
  await login(page, account)
  await send(page, gate.prompt)
  const answer = page.getByRole('article', { name: '知舟的回复', exact: true })
  await expect(answer).toContainText('已收到部分回答')
  await expect(answer.getByRole('button', { name: '复制回复', exact: true })).toHaveCount(0)
  await gate.release()
  await expect(await finished(page)).toContainText('已收到部分回答，现在完成。')
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
  await (await sidebar(page)).getByRole('button', { name: '退出登录', exact: true }).click()
  await expect(page).toHaveURL(/\/login/)
  await expect.poll(gate.closed).toBe(true)
  const other = await createAccount(request)
  await login(page, other)
  await expect(await sidebar(page)).toContainText('还没有对话')
  await closeSidebar(page)
  await expect(page.getByRole('article')).toHaveCount(0)
})
