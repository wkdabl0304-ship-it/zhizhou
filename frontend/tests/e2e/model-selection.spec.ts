/** 受限模型选择真实浏览器验收：与配置管理共用串行随机库，每例隔离默认、启停及选择版本。 */
import {
  test,
  control,
  provider,
  model,
  headers,
  openProvider,
  closeProvider,
  returnToChat,
} from '../support/playwright/model-config'
import {
  expect,
  login,
  send,
  finished,
  sidebar,
  closeSidebar,
} from '../support/playwright/fixtures'
import type { Page } from '@playwright/test'
import {
  openPicker,
  closePicker,
  chooseModel,
  refreshModels,
  openReasoning,
  closeReasoning,
} from '../support/playwright/model-selection'

/** 选择并重新展开参数区，供受限推理场景继续核对和编辑。 */
async function choose(page: Page, name: string): Promise<void> {
  await chooseModel(page, name)
}
/** 从原会话目录打开历史，验证页面重载后由服务端恢复选择。 */
async function reopen(page: Page, title: string): Promise<void> {
  const navigation = await sidebar(page)
  await navigation.getByRole('button', { name: title, exact: true }).click()
  await closeSidebar(page)
  await expect(page.getByRole('heading', { level: 1, name: title, exact: true })).toBeVisible()
}

test('无默认手动选择方案，刷新恢复，连接和模型启停互不级联', async ({
  page,
  account,
}, testInfo) => {
  await login(page, account)
  await page.goto('/models')
  await provider(page)
  await model(page, '固定问答')
  await closeProvider(page)
  await returnToChat(page)
  await page.getByRole('textbox', { name: '消息内容' }).fill('手动选择固定方案')
  await expect(page.getByRole('button', { name: '发送消息', exact: true })).toBeDisabled()
  await choose(page, '固定问答')
  await expect(page.getByRole('switch', { name: '深度思考', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '设置推理强度', exact: true })).toBeEnabled()
  await expect(page.locator('[name="chat_reasoning_mode"]')).toHaveCount(0)
  // 单个入口位于输入框工具栏且在发送按钮左边；浮层不挤占聊天正文。
  const trigger = page.getByRole('button', { name: '选择聊天模型', exact: true })
  await expect(page.locator('.composer-send .chat-model-trigger')).toHaveCount(1)
  const triggerBox = await trigger.boundingBox(),
    sendBox = await page.getByRole('button', { name: '发送消息', exact: true }).boundingBox()
  expect(triggerBox!.x + triggerBox!.width).toBeLessThanOrEqual(sendBox!.x)
  expect(
    Math.abs(triggerBox!.y + triggerBox!.height / 2 - sendBox!.y - sendBox!.height / 2),
  ).toBeLessThan(2)
  await openPicker(page)
  const menu = page.getByRole('dialog', { name: '选择聊天模型', exact: true })
  // 顶部管理入口仍可用键盘访问，默认焦点和方向键则优先服务模型选择。
  await expect
    .poll(() =>
      menu
        .getByRole('listbox')
        .evaluate(
          (element) =>
            element === document.activeElement || element.contains(document.activeElement),
        ),
    )
    .toBe(true)
  await expect(menu.getByRole('option').first()).toBeEnabled()
  await page.keyboard.press('Home')
  await expect(menu.getByRole('option').first()).toBeFocused()
  await page.keyboard.press('Shift+Tab')
  await expect(menu.getByRole('link', { name: '前往模型管理', exact: true })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(menu.getByRole('option').first()).toBeFocused()
  const menuTitleBox = await menu.getByText('选择模型', { exact: true }).boundingBox()
  const manageBox = await menu
    .getByRole('link', { name: '前往模型管理', exact: true })
    .boundingBox()
  expect(manageBox!.x).toBeGreaterThan(menuTitleBox!.x + menuTitleBox!.width)
  expect(Math.abs(manageBox!.y - menuTitleBox!.y)).toBeLessThan(5)
  await expect(menu.getByText('请选择模型方案', { exact: true })).toHaveCount(0)
  const menuBox = await page
    .getByRole('dialog', { name: '选择聊天模型', exact: true })
    .boundingBox()
  expect(menuBox!.width).toBeLessThanOrEqual(302)
  expect(menuBox!.x).toBeGreaterThanOrEqual(0)
  expect(menuBox!.x + menuBox!.width).toBeLessThanOrEqual(page.viewportSize()!.width)
  await page.screenshot({ path: testInfo.outputPath('composer-model-menu.png'), fullPage: true })
  await closePicker(page)
  await expect(trigger).toBeFocused()
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
  await openPicker(page)
  await page.getByRole('link', { name: '前往模型管理', exact: true }).click()
  await openProvider(page)
  const card = page.getByRole('article', { name: '模型方案：固定问答', exact: true })
  await card.getByRole('switch').click()
  await expect(card).toContainText('已停用')
  await expect(card.getByRole('button', { name: '测试', exact: true })).toBeEnabled()
  await page.getByRole('switch', { name: '启用供应商连接 我的 DeepSeek', exact: true }).click()
  await page.getByRole('switch', { name: '启用供应商连接 我的 DeepSeek', exact: true }).click()
  await expect(card).toContainText('已停用')
  await closeProvider(page)
  await returnToChat(page)
  await expect(page.getByRole('region', { name: '聊天模型状态' })).toContainText('原模型方案已停用')
  await expect(page.getByRole('textbox', { name: '消息内容' })).toHaveValue('停用后保留的草稿')
  await expect(page.getByRole('button', { name: '发送消息', exact: true })).toBeDisabled()
  await openPicker(page)
  await page.getByRole('link', { name: '前往模型管理', exact: true }).click()
  await openProvider(page)
  await card.getByRole('switch').click()
  await closeProvider(page)
  await returnToChat(page)
  await expect(page.getByRole('button', { name: '发送消息', exact: true })).toBeEnabled()
  await page.screenshot({ path: testInfo.outputPath('selection-restored.png'), fullPage: true })
})

test('管理开放档位白名单，会话切换立即保存，多端冲突保留草稿并要求确认', async ({
  page,
  account,
  request,
}, testInfo) => {
  await login(page, account)
  await page.goto('/models')
  await provider(page)
  await model(page, '受限问答')
  const card = page.getByRole('article', { name: '模型方案：受限问答', exact: true })
  await card.getByRole('button', { name: '高级设置', exact: true }).click()
  const editor = page.getByRole('dialog', { name: '编辑模型方案', exact: true })
  await expect(editor.locator('[name="reasoning_mode"], [name="reasoning_policy"]')).toHaveCount(0)
  await expect(editor.locator('[name="allow_off"]')).toBeChecked()
  await editor.locator('[name="allow_effort_max"]').uncheck()
  await editor.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(editor).not.toBeVisible()
  await closeProvider(page)
  await returnToChat(page)
  await choose(page, '受限问答')
  await page.getByRole('textbox', { name: '消息内容', exact: true }).fill('切换思考保留的草稿')
  await openReasoning(page)
  const slider = page.getByRole('slider', { name: '推理强度', exact: true })
  await expect(slider).toHaveAttribute('max', '2')
  await slider.focus()
  await page.keyboard.press('Home')
  await expect(slider).toHaveAttribute('aria-valuetext', '关闭')
  await expect(page.getByRole('button', { name: '设置推理强度', exact: true })).toContainText(
    '关闭',
  )
  await expect(page.getByRole('dialog', { name: '设置推理强度', exact: true })).toBeVisible()
  await slider.focus()
  await page.keyboard.press('ArrowRight')
  await expect(slider).toHaveAttribute('aria-valuetext', '低')
  await expect(page.getByRole('textbox', { name: '消息内容', exact: true })).toHaveValue(
    '切换思考保留的草稿',
  )
  await expect(page.getByRole('article')).toHaveCount(0)
  await page.screenshot({ path: testInfo.outputPath('reasoning-strength.png'), fullPage: true })
  await closeReasoning(page)
  await send(page, '受限档位会话')
  await finished(page)
  const auth = await headers(request, account),
    base = control().url
  const previous = await (await request.get(`${base}/api/conversations`, { headers: auth })).json()
  await openReasoning(page)
  await page.getByRole('slider', { name: '推理强度', exact: true }).focus()
  await page.keyboard.press('End')
  await expect(page.getByText('正在保存会话选择…', { exact: true })).not.toBeVisible()
  await closeReasoning(page)
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
  await expect(page.getByRole('button', { name: '设置推理强度', exact: true })).toContainText(
    '关闭',
  )
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
  await refreshModels(page)
  await expect(page.getByRole('region', { name: '聊天模型状态' })).toContainText(
    '原推理设置超出当前限制',
  )
  await expect(page.getByRole('button', { name: '发送消息', exact: true })).toBeDisabled()
  await choose(page, '受限问答')
  await closePicker(page)
  await expect(page.getByRole('button', { name: '发送消息', exact: true })).toBeEnabled()
  // 超管仅保留高档时，以右端满轨道表达开启；只读展示不能增加额外可选档位。
  await openReasoning(page)
  const singleSlider = page.getByRole('slider', { name: '推理强度', exact: true })
  await expect(singleSlider).toBeDisabled()
  await expect(singleSlider).toHaveValue('1')
  await expect(singleSlider).toHaveAttribute('max', '1')
  await expect(singleSlider).toHaveAttribute('aria-valuetext', '高')
  await expect(page.locator('.reasoning-ticks')).toHaveText('高')
  await page.screenshot({
    path: testInfo.outputPath('single-reasoning-strength.png'),
    fullPage: true,
  })
  await closeReasoning(page)
  await send(page, '单档思考仍可正常续聊')
  await finished(page)
})

test('管理预算闭区间，聊天确认有效整数后保存，刷新恢复具体预算', async ({
  page,
  account,
}, testInfo) => {
  await login(page, account)
  await page.goto('/models')
  const navigation = await sidebar(page)
  await navigation.getByRole('button', { name: /外观.*浅色/ }).click()
  await page.getByRole('menuitemradio', { name: '深色', exact: true }).click()
  await closeSidebar(page)
  await provider(page, '预算连接', 'anthropic')
  await model(page, '预算问答', 'Claude Haiku 4.5')
  await page
    .getByRole('article', { name: '模型方案：预算问答', exact: true })
    .getByRole('button', { name: '高级设置' })
    .click()
  const editor = page.getByRole('dialog', { name: '编辑模型方案', exact: true })
  await editor.locator('[name="policy_budget_max"]').fill('8192')
  await editor.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(editor).not.toBeVisible()
  await closeProvider(page)
  await returnToChat(page)
  await choose(page, '预算问答')
  await openReasoning(page)
  await page.locator('[name="chat_budget"]').fill('1023')
  await page
    .getByRole('form', { name: '思考强度设置', exact: true })
    .getByRole('button', { name: '应用预算', exact: true })
    .click()
  await expect(page.getByRole('form', { name: '思考强度设置', exact: true })).toContainText('整数')
  await page.locator('[name="chat_budget"]').fill('1024')
  await page.getByRole('button', { name: '应用预算', exact: true }).click()
  await closeReasoning(page)
  await send(page, '预算选择会话')
  await finished(page)
  await openReasoning(page)
  await page.locator('[name="chat_budget"]').fill('8192')
  await page.getByRole('button', { name: '应用预算', exact: true }).click()
  await expect(page.getByText('正在保存会话选择…', { exact: true })).not.toBeVisible()
  await closeReasoning(page)
  await page.reload()
  await reopen(page, '预算选择会话')
  await openReasoning(page)
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
  await closeProvider(page)
  await returnToChat(page)
  await choose(page, '生成方案')
  await closePicker(page)
  const gate = await modelGate('hold')
  await send(page, gate.prompt)
  await expect(page.getByRole('button', { name: '发送消息', exact: true })).toBeDisabled()
  await openPicker(page)
  await expect(page.getByRole('listbox', { name: '聊天模型方案', exact: true })).toHaveAttribute(
    'aria-disabled',
    'true',
  )
  await expect(page.getByRole('option').first()).toBeDisabled()
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
  await refreshModels(page)
  await gate.release()
  await finished(page)
  await expect(page.getByRole('region', { name: '聊天模型状态' })).toContainText('原模型方案已停用')
  await page.getByRole('textbox', { name: '消息内容' }).fill('下一轮不可误发')
  await expect(page.getByRole('button', { name: '发送消息', exact: true })).toBeDisabled()
  expect(await gate.closed()).toBe(true)
})
