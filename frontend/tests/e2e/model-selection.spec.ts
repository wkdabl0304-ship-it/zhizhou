/** 受限模型选择真实浏览器验收：与配置管理共用串行随机库，每例隔离默认、启停及选择版本。 */
import { test, control, provider, model, headers } from '../support/playwright/model-config'
import {
  expect,
  login,
  send,
  finished,
  sidebar,
  closeSidebar,
} from '../support/playwright/fixtures'
import type { Page } from '@playwright/test'

/** 展开聊天模型控件，按可见方案名称选择，既有会话会立即经 PATCH 保存。 */
async function choose(page: Page, name: string): Promise<void> {
  await openPicker(page)
  const option = page.getByRole('option', { name: new RegExp(`^${name} ·`) })
  const id = await option.getAttribute('value')
  expect(id).toBeTruthy()
  await page.getByLabel('聊天模型方案', { exact: true }).selectOption(id!)
  await expect(page.getByText('正在保存会话选择…', { exact: true })).not.toBeVisible()
}
/** 只在控件收起时展开，避免反复点击将已经显示的输入区关闭。 */
async function openPicker(page: Page): Promise<void> {
  if ((await page.locator('.chat-model-picker').getAttribute('open')) === null)
    await page.locator('.chat-model-picker summary').click()
}
/** 收起模型面板，避免覆盖后续聊天或管理入口。 */
async function closePicker(page: Page): Promise<void> {
  if ((await page.locator('.chat-model-picker').getAttribute('open')) !== null)
    await page.locator('.chat-model-picker summary').click()
}
/** 从原会话目录打开历史，验证页面重载后由服务端恢复选择。 */
async function reopen(page: Page, title: string): Promise<void> {
  const navigation = await sidebar(page)
  await navigation.getByRole('button', { name: title, exact: true }).click()
  await closeSidebar(page)
  await expect(page.getByRole('heading', { level: 1, name: title, exact: true })).toBeVisible()
}

test('无默认手动选择固定方案，刷新恢复，连接和模型启停互不级联', async ({
  page,
  account,
}, testInfo) => {
  await login(page, account)
  await page.goto('/models')
  await provider(page)
  await model(page, '固定问答')
  await page.getByRole('link', { name: '返回聊天', exact: true }).click()
  await page.getByRole('textbox', { name: '消息内容' }).fill('手动选择固定方案')
  await expect(page.getByRole('button', { name: '发送消息', exact: true })).toBeDisabled()
  await choose(page, '固定问答')
  await expect(page.getByText(/固定推理设置 ·/)).toBeVisible()
  await expect(page.locator('[name="chat_reasoning_mode"]')).toHaveCount(0)
  await closePicker(page)
  const firstRequest = page.waitForRequest(
    (sent) => sent.url().endsWith('/api/chat') && sent.method() === 'POST',
  )
  await page.getByRole('button', { name: '发送消息', exact: true }).click()
  await finished(page)
  const firstBody = (await firstRequest).postDataJSON()
  expect(firstBody.model_selection.model_configuration_id).toBeTruthy()
  expect(['off', 'effort', 'budget']).toContain(firstBody.model_selection.reasoning.mode)
  expect(firstBody).not.toHaveProperty('model_selection_version')
  await page.reload()
  await reopen(page, '手动选择固定方案')
  await expect(page.getByRole('region', { name: '聊天模型状态' })).toContainText('固定问答')
  await page.getByRole('textbox', { name: '消息内容' }).fill('停用后保留的草稿')
  await page.getByRole('link', { name: '前往模型管理', exact: true }).click()
  const card = page.getByRole('article', { name: '模型方案：固定问答', exact: true })
  await card.getByRole('button', { name: '停用', exact: true }).click()
  await page.getByRole('button', { name: '确认停用', exact: true }).click()
  await expect(card).toContainText('已停用')
  await expect(card.getByRole('button', { name: '测试', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: '停用连接', exact: true }).click()
  await page.getByRole('button', { name: '确认停用', exact: true }).click()
  await page.getByRole('button', { name: '启用连接', exact: true }).click()
  await expect(card).toContainText('已停用')
  await page.getByRole('link', { name: '返回聊天', exact: true }).click()
  await expect(page.getByRole('region', { name: '聊天模型状态' })).toContainText('原模型方案已停用')
  await expect(page.getByRole('textbox', { name: '消息内容' })).toHaveValue('停用后保留的草稿')
  await expect(page.getByRole('button', { name: '发送消息', exact: true })).toBeDisabled()
  await page.getByRole('link', { name: '前往模型管理', exact: true }).click()
  await card.getByRole('button', { name: '启用', exact: true }).click()
  await page.getByRole('link', { name: '返回聊天', exact: true }).click()
  await expect(page.getByRole('button', { name: '发送消息', exact: true })).toBeEnabled()
  await page.screenshot({ path: testInfo.outputPath('selection-restored.png'), fullPage: true })
})

test('管理开放档位白名单，会话切换立即保存，多端冲突保留草稿并要求确认', async ({
  page,
  account,
  request,
}) => {
  await login(page, account)
  await page.goto('/models')
  await provider(page)
  await model(page, '受限问答')
  const card = page.getByRole('article', { name: '模型方案：受限问答', exact: true })
  await card.getByRole('button', { name: '编辑', exact: true }).click()
  const editor = page.getByRole('dialog', { name: '编辑模型方案', exact: true })
  await editor.locator('[name="reasoning_mode"]').selectOption('effort')
  await editor.locator('[name="effort"]').selectOption('high')
  await editor.locator('[name="reasoning_policy"]').selectOption('selectable')
  await editor.locator('[name="allow_off"]').check()
  await editor.locator('[name="allow_effort_max"]').uncheck()
  await editor.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(editor).not.toBeVisible()
  await page.getByRole('link', { name: '返回聊天', exact: true }).click()
  await choose(page, '受限问答')
  await expect(page.locator('[name="chat_effort"] option')).toHaveText(['low', 'high'])
  await page.locator('[name="chat_effort"]').selectOption('low')
  await closePicker(page)
  await send(page, '受限档位会话')
  await finished(page)
  const auth = await headers(request, account),
    base = control().url
  const previous = await (await request.get(`${base}/api/conversations`, { headers: auth })).json()
  await openPicker(page)
  await page.locator('[name="chat_effort"]').selectOption('high')
  await expect(page.getByText('正在保存会话选择…', { exact: true })).not.toBeVisible()
  await closePicker(page)
  const listed = await (await request.get(`${base}/api/conversations`, { headers: auth })).json()
  const conversation = listed.data.items[0] as {
    conversation_id: string
    model_selection_version: number
    last_message_at: string
    model_selection: { model_configuration_id: string }
  }
  expect(conversation.model_selection_version).toBe(2)
  expect(conversation.last_message_at).toBe(previous.data.items[0].last_message_at)
  const changed = await request.patch(
    `${base}/api/conversations/${conversation.conversation_id}/model-selection`,
    {
      headers: auth,
      data: {
        model_selection_version: 2,
        model_selection: { ...conversation.model_selection, reasoning: { mode: 'off' } },
      },
    },
  )
  expect((await changed.json()).code).toBe(0)
  await page.getByRole('textbox', { name: '消息内容' }).fill('冲突后保留消息')
  await page.getByRole('button', { name: '发送消息', exact: true }).click()
  await expect(page.getByRole('region', { name: '聊天模型状态' })).toContainText('请确认')
  await expect(page.getByRole('textbox', { name: '消息内容' })).toHaveValue('冲突后保留消息')
  await expect(page.getByRole('article')).toHaveCount(2)
  await expect(page.locator('.chat-model-picker summary')).toContainText('关闭思考')
  // 收紧后台范围后，保存的关闭思考选择必须失效，不能静默替换成高档。
  const configs = await (
    await request.get(`${base}/api/model-config/models`, { headers: auth })
  ).json()
  const config = configs.data[0] as { id: string; version: number }
  const narrowed = await request.patch(`${base}/api/model-config/models/${config.id}`, {
    headers: auth,
    data: {
      version: config.version,
      reasoning: { mode: 'effort', effort: 'high' },
      reasoning_policy: {
        mode: 'selectable',
        allowed_modes: ['effort'],
        effort_options: ['high'],
        budget: null,
      },
    },
  })
  expect((await narrowed.json()).code).toBe(0)
  await page.getByRole('button', { name: '刷新模型选项', exact: true }).click()
  await expect(page.getByRole('region', { name: '聊天模型状态' })).toContainText(
    '原推理设置超出当前限制',
  )
  await expect(page.getByRole('button', { name: '发送消息', exact: true })).toBeDisabled()
  await choose(page, '受限问答')
  await closePicker(page)
  await expect(page.getByRole('button', { name: '发送消息', exact: true })).toBeEnabled()
})

test('管理预算闭区间，聊天确认有效整数后保存，刷新恢复具体预算', async ({
  page,
  account,
}, testInfo) => {
  await login(page, account)
  await page.goto('/models')
  await provider(page, '预算连接', 'anthropic')
  await page.getByRole('button', { name: '添加模型方案', exact: true }).click()
  const editor = page.getByRole('dialog', { name: '添加模型方案', exact: true })
  await editor.locator('[name="name"]').fill('预算问答')
  await editor
    .locator('[name="catalog_model_id"]')
    .selectOption('anthropic:claude-haiku-4-5-20251001')
  await editor.locator('[name="reasoning_mode"]').selectOption('budget')
  await editor.locator('[name="reasoning_policy"]').selectOption('selectable')
  await editor.locator('[name="policy_budget_max"]').fill('8192')
  await editor.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(editor).not.toBeVisible()
  await page.getByRole('link', { name: '返回聊天', exact: true }).click()
  await choose(page, '预算问答')
  await page.locator('[name="chat_budget"]').fill('1023')
  await page
    .getByRole('form', { name: '聊天模型选择', exact: true })
    .getByRole('button', { name: '应用选择', exact: true })
    .click()
  await expect(page.getByRole('form', { name: '聊天模型选择', exact: true })).toContainText('整数')
  await page.locator('[name="chat_budget"]').fill('1024')
  await page.getByRole('button', { name: '应用选择', exact: true }).click()
  await closePicker(page)
  await send(page, '预算选择会话')
  await finished(page)
  await openPicker(page)
  await page.locator('[name="chat_budget"]').fill('8192')
  await page.getByRole('button', { name: '应用选择', exact: true }).click()
  await expect(page.getByText('正在保存会话选择…', { exact: true })).not.toBeVisible()
  await closePicker(page)
  await page.reload()
  await reopen(page, '预算选择会话')
  await openPicker(page)
  await expect(page.locator('[name="chat_budget"]')).toHaveValue('8192')
  await page.screenshot({ path: testInfo.outputPath('budget-picker.png'), fullPage: true })
})

test('生成中禁止切换，后台停用不终止本轮，结束后阻止下一轮发送', async ({
  page,
  account,
  request,
  modelGate,
}) => {
  await login(page, account)
  await page.goto('/models')
  await provider(page)
  await model(page, '生成方案')
  await page.getByRole('link', { name: '返回聊天', exact: true }).click()
  await choose(page, '生成方案')
  await closePicker(page)
  const gate = await modelGate('hold')
  await send(page, gate.prompt)
  await expect(page.getByRole('button', { name: '发送消息', exact: true })).toBeDisabled()
  await openPicker(page)
  await expect(page.getByLabel('聊天模型方案', { exact: true })).toBeDisabled()
  await closePicker(page)
  const auth = await headers(request, account),
    base = control().url
  const listed = await (
    await request.get(`${base}/api/model-config/models`, { headers: auth })
  ).json()
  const config = listed.data[0] as { id: string; version: number }
  expect(
    (
      await (
        await request.patch(`${base}/api/model-config/models/${config.id}`, {
          headers: auth,
          data: { version: config.version, enabled: false },
        })
      ).json()
    ).code,
  ).toBe(0)
  await page.getByRole('button', { name: '刷新模型选项', exact: true }).click()
  await gate.release()
  await finished(page)
  await expect(page.getByRole('region', { name: '聊天模型状态' })).toContainText('原模型方案已停用')
  await page.getByRole('textbox', { name: '消息内容' }).fill('下一轮不可误发')
  await expect(page.getByRole('button', { name: '发送消息', exact: true })).toBeDisabled()
  expect(await gate.closed()).toBe(true)
})
