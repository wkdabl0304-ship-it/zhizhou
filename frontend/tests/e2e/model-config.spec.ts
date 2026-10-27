/** 模型管理全链路：真实页面与随机库，配置重置及 HTTP 辅助由共用 fixture 负责。 */
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
import { openPicker, refreshModels } from '../support/playwright/model-selection'
import { expect, login, send, finished, closeSidebar } from '../support/playwright/fixtures'

test('首次配置、主动测试、设默认后返回聊天保留草稿，刷新仍可使用', async ({
  page,
  account,
}, testInfo) => {
  await login(page, account)
  await page.getByRole('textbox', { name: '消息内容' }).fill('配置前的草稿')
  await expect(page.getByRole('button', { name: '发送消息', exact: true })).toBeDisabled()
  await openPicker(page)
  await page.getByRole('link', { name: '前往模型管理', exact: true }).click()
  await expect(page.locator('.provider-brand-card')).toHaveCount(4)
  const compactTitle = page.getByRole('heading', { level: 1, name: '模型管理', exact: true })
  await expect(compactTitle).toBeVisible()
  await expect(page.getByText('MODEL PROVIDERS', { exact: true })).toBeVisible()
  expect((await compactTitle.boundingBox())!.height).toBeLessThan(40)
  await expect(page.locator('.chat-header')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '刷新配置', exact: true })).toHaveCount(0)
  await expect(page.getByRole('link', { name: '返回聊天', exact: true })).toHaveCount(0)

  await expect(page.getByRole('region', { name: '全局默认模型', includeHidden: true })).toHaveCount(
    0,
  )
  await expect
    .poll(() =>
      page
        .locator('.provider-brand-card img')
        .evaluateAll((images) =>
          images.every(
            (image) =>
              (image as HTMLImageElement).complete && (image as HTMLImageElement).naturalWidth > 0,
          ),
        ),
    )
    .toBe(true)
  // 大屏与手机分别留图，验证首次空状态及新增供应商后的真实比例，不维护像素基线。
  if (testInfo.project.name === 'model-config-desktop')
    await page.setViewportSize({ width: 1920, height: 945 })
  await page.screenshot({ path: testInfo.outputPath('empty-state.png'), fullPage: true })
  // 通过真实外观菜单切换主题，留存暗色卡片及后续模型弹窗供视觉检查。
  const navigationTrigger = page.getByRole('button', { name: '打开侧栏', exact: true })
  if (await navigationTrigger.isVisible()) await navigationTrigger.click()
  await page.getByRole('button', { name: /外观.*浅色/ }).click()
  await page.getByRole('menuitemradio', { name: '深色', exact: true }).click()
  await closeSidebar(page)
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  // Logo 的单色反色只影响图形，不能把整页过滤成纯白。
  expect(await page.locator('html').evaluate((element) => getComputedStyle(element).filter)).toBe(
    'none',
  )
  expect(
    await page
      .locator('.provider-brand-card[data-provider="openai"] img')
      .evaluate((element) => getComputedStyle(element).filter),
  ).toContain('invert(1)')
  expect(
    await page
      .locator('.provider-brand-card[data-provider="deepseek"] img')
      .evaluate((element) => getComputedStyle(element).filter),
  ).toBe('none')
  await page.screenshot({ path: testInfo.outputPath('providers-dark.png'), fullPage: true })
  await provider(page)
  await expect(page.getByRole('region', { name: '供应商连接' })).toContainText('我的 DeepSeek')
  await expect(page.getByRole('switch', { name: /^启用模型/, checked: false })).toHaveCount(2)
  await expect(page.locator('.config-default')).toHaveCount(0)
  await expect(page.getByText('当前默认', { exact: true })).toHaveCount(0)
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    .toBe(true)
  await page.screenshot({ path: testInfo.outputPath('provider-added.png'), fullPage: true })
  await model(page)
  const card = page.getByRole('article', { name: '模型方案：日常问答', exact: true })
  // 空格操作真实开关，关闭后重新开启仍复用同一方案，不弹出停用确认。
  const modelSwitch = card.getByRole('switch')
  await modelSwitch.focus()
  await page.keyboard.press('Space')
  await expect(modelSwitch).not.toBeChecked()
  await expect(page.getByRole('dialog')).toHaveCount(1)
  await modelSwitch.focus()
  await page.keyboard.press('Space')
  await expect(modelSwitch).toBeChecked()
  await expect(card.getByRole('button', { name: '测试', exact: true })).toBeVisible()
  await expect(card.getByText('文本流通过', { exact: false })).toHaveCount(0)
  await expect(card.getByRole('button', { name: '高级设置', exact: true })).toBeVisible()
  await expect(card.getByRole('button', { name: '删除', exact: true })).toBeVisible()
  await expect(page.getByText('更多操作', { exact: true })).toHaveCount(0)
  await page.screenshot({ path: testInfo.outputPath('model-ready.png'), fullPage: true })
  await card.getByRole('button', { name: '设为默认', exact: true }).click()
  await expect(
    page.getByRole('article', { name: '模型方案：日常问答', exact: true }),
  ).toContainText('当前默认')
  await card.getByRole('button', { name: '测试', exact: true }).click()
  await expect(page.getByRole('dialog', { name: '测试模型连接', exact: true })).toHaveCount(0)
  await expect(card).toContainText('文本流通过')
  await expect(page.getByText('测试已结束，请查看模型测试结果。', { exact: true })).toHaveCount(0)
  await closeProvider(page)
  await returnToChat(page)
  await expect(page.getByRole('textbox', { name: '消息内容' })).toHaveValue('配置前的草稿')
  await page.getByRole('button', { name: '发送消息', exact: true }).click()
  await expect(await finished(page)).toContainText('配置前的草稿')
  await page.reload()
  await expect(page.getByRole('region', { name: '聊天模型状态' })).toContainText('日常问答')
  await send(page, '刷新后仍可发送')
  await expect(await finished(page)).toContainText('刷新后仍可发送')
})

test('编辑、切换和清除默认，并按引用顺序删除模型及供应商', async ({ page, account }, testInfo) => {
  await login(page, account)
  await page.goto('/models')
  await provider(page)
  await model(page)
  const first = page.getByRole('article', { name: '模型方案：日常问答', exact: true })
  await first.getByRole('button', { name: '设为默认' }).click()
  await first.getByRole('button', { name: '删除', exact: true }).click()
  await expect(page.getByRole('dialog', { name: '删除模型方案？', exact: true })).toContainText(
    '自动清除全局默认',
  )
  await page
    .getByRole('dialog', { name: '删除模型方案？', exact: true })
    .getByRole('button', { name: '取消', exact: true })
    .click()
  await page.getByRole('button', { name: '删除供应商', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('仍被引用')
  await model(page, '深入思考')
  const second = page.getByRole('article', { name: '模型方案：深入思考', exact: true })
  await second.getByRole('button', { name: '高级设置', exact: true }).click()
  const editor = page.getByRole('dialog', { name: '编辑模型方案', exact: true })
  await editor.locator('[name="reasoning_mode"]').selectOption('effort')
  await editor.locator('[name="effort"]').selectOption('max')
  await editor.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(editor).not.toBeVisible()
  await expect(second).toContainText('推理 · 最高')
  // 保存实际桌面和窄屏界面供人工核对，不将像素截图作为通过标准。
  await page.screenshot({ path: testInfo.outputPath('model-management.png'), fullPage: true })
  await second.getByRole('button', { name: '设为默认' }).click()
  await first.getByRole('button', { name: '删除', exact: true }).click()
  await page.getByRole('button', { name: '确认删除', exact: true }).click()
  await expect(first).toHaveCount(0)
  await second.getByRole('button', { name: '清除默认', exact: true }).click()
  await expect(page.getByRole('dialog', { name: '清除全局默认模型？' })).toHaveCount(0)
  await expect(page.locator('.config-default')).toHaveCount(0)
  await expect(page.getByText('当前默认', { exact: true })).toHaveCount(0)
  await openProvider(page)
  await second.getByRole('button', { name: '删除', exact: true }).click()
  await page.getByRole('button', { name: '确认删除', exact: true }).click()
  await expect(second).toHaveCount(0)
  await page.getByRole('button', { name: '删除供应商', exact: true }).click()
  await page.getByRole('button', { name: '确认删除', exact: true }).click()
  await closeProvider(page)
  await expect(page.locator('.provider-brand-card')).toHaveCount(4)
})

// 全局默认只初始化尚未选择的页面，清除后不能覆盖用户已经看到并确认的具体选择。
test('其他客户端清除默认不覆盖本地选择，既有会话继续使用确认版本', async ({
  page,
  account,
  request,
}) => {
  await login(page, account)
  await page.goto('/models')
  await provider(page)
  await model(page)
  await page
    .getByRole('article', { name: '模型方案：日常问答', exact: true })
    .getByRole('button', { name: '设为默认', exact: true })
    .click()
  await expect(
    page.getByRole('article', { name: '模型方案：日常问答', exact: true }),
  ).toContainText('当前默认')
  await closeProvider(page)
  await returnToChat(page)
  await expect(page.getByRole('region', { name: '聊天模型状态' })).toContainText('日常问答')
  const auth = await headers(request, account),
    endpoint = `${control().url}/api/model-config/default`
  const selected = await (await request.get(endpoint, { headers: auth })).json()
  const cleared = await request.put(endpoint, {
    headers: auth,
    data: { version: selected.data.version, model_configuration_id: null },
  })
  expect((await cleared.json()).code).toBe(0)
  await send(page, '默认已从其他客户端清除')
  await finished(page)
  await refreshModels(page)
  await expect(page.getByRole('region', { name: '聊天模型状态' })).toContainText('日常问答')
  await expect(page).toHaveURL(/\/$/)
  const history = await request.get(`${control().url}/api/conversations?limit=20`, {
    headers: auth,
  })
  const rows = (await history.json()).data.items
  expect(rows).toHaveLength(1)
  const continuing = page.waitForRequest(
    (sent) => sent.url().endsWith('/api/chat') && sent.method() === 'POST',
  )
  await send(page, '沿用会话自己的选择')
  const body = (await continuing).postDataJSON()
  expect(body).toEqual({
    message: '沿用会话自己的选择',
    conversation_id: rows[0].conversation_id,
    model_selection_version: rows[0].model_selection_version,
  })
  await finished(page)
})

// 百炼现成兼容地址的配置、测试、修改及聊天都经过正式 API 和隔离数据库。
test('百炼粘贴 Base URL 即可配置，修改地址保留密钥并可继续聊天', async ({
  page,
  account,
}, testInfo) => {
  await login(page, account)
  await page.goto('/models')
  await openProvider(page, 'bailian')
  await page.getByRole('button', { name: '添加连接', exact: true }).click()
  const editor = page.getByRole('dialog', { name: '添加供应商配置', exact: true })
  await expect(editor.locator('[name="endpoint"]')).toHaveCount(0)
  await expect(editor.locator('[name="workspace"]')).toHaveCount(0)
  await editor.locator('[name="name"]').fill('我的百炼')
  await editor.locator('[name="api_key"]').fill('e2e-bailian-fake-key')
  await editor
    .getByLabel('Base URL', { exact: true })
    .fill('https://ws-e2e.cn-beijing.maas.aliyuncs.com/api/v1')
  await editor.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(editor.getByRole('alert')).toContainText('OpenAI 兼容地址')
  const address = 'https://ws-e2e.cn-beijing.maas.aliyuncs.com/compatible-mode/v1'
  await editor.getByLabel('Base URL', { exact: true }).fill(`  ${address}/  `)
  await editor.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(editor).not.toBeVisible()
  await expect(page.getByRole('region', { name: '供应商连接' })).toContainText(address)
  await model(page, '百炼日常问答')
  const card = page.getByRole('article', { name: '模型方案：百炼日常问答', exact: true })
  await card.getByRole('button', { name: '设为默认', exact: true }).click()
  await card.getByRole('button', { name: '测试', exact: true }).click()
  await expect(card).toContainText('文本流通过')
  await page.getByRole('button', { name: '编辑供应商', exact: true }).click()
  const editing = page.getByRole('dialog', { name: '编辑供应商配置', exact: true })
  await expect(editing.getByLabel('Base URL', { exact: true })).toHaveValue(address)
  await expect(editing.locator('[name="api_key"]')).toHaveValue('')
  await page.screenshot({ path: testInfo.outputPath('bailian-base-url.png'), fullPage: true })
  const changed = 'https://ws-e2e.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1'
  await editing.getByLabel('Base URL', { exact: true }).fill(changed)
  await editing.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(editing).not.toBeVisible()
  await expect(page.getByRole('region', { name: '供应商连接' })).toContainText(changed)
  await expect(card).toContainText('配置已修改，请重新测试')
  await closeProvider(page)
  await returnToChat(page)
  await send(page, '使用百炼地址配置聊天')
  await finished(page)
  await page.reload()
  await page.goto('/models')
  await openProvider(page, 'bailian')
  await expect(page.getByRole('region', { name: '供应商连接' })).toContainText(changed)
  await expect(
    page.getByRole('article', { name: '模型方案：百炼日常问答', exact: true }),
  ).toContainText('当前默认')
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    .toBe(true)
})

test('另一个客户端修改配置后本地草稿保留，读取最新版本后才能保存', async ({
  page,
  account,
  request,
}) => {
  await login(page, account)
  await page.goto('/models')
  await provider(page)
  await page.getByRole('button', { name: '编辑供应商', exact: true }).click()
  const editor = page.getByRole('dialog', { name: '编辑供应商配置', exact: true })
  await expect(editor.locator('[name="api_key"]')).toHaveValue('')
  await editor.locator('[name="name"]').fill('本地未保存名称')
  const auth = await headers(request, account),
    endpoint = `${control().url}/api/model-config/provider-configurations`
  const listed = await (await request.get(endpoint, { headers: auth })).json()
  const config = listed.data[0] as { id: string; version: number }
  const patched = await request.patch(`${endpoint}/${config.id}`, {
    headers: auth,
    data: { version: config.version, name: '远端修改名称' },
  })
  expect((await patched.json()).code).toBe(0)
  await editor.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(editor.getByRole('alert')).toContainText('已被修改')
  await expect(editor.locator('[name="name"]')).toHaveValue('本地未保存名称')
  await editor.getByRole('button', { name: '关闭', exact: true }).click()
  await page.getByRole('button', { name: '放弃更改', exact: true }).click()
  await page.getByRole('button', { name: '编辑供应商', exact: true }).click()
  await expect(editor.locator('[name="name"]')).toHaveValue('远端修改名称')
  await editor.locator('[name="name"]').fill('基于新版本保存')
  await editor.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(editor).not.toBeVisible()
  await expect(page.getByRole('region', { name: '供应商连接' })).toContainText('基于新版本保存')
})

test('目录推理预算与输出约束即时提示，正确参数才能保存', async ({ page, account }) => {
  await login(page, account)
  await page.goto('/models')
  await provider(page, 'Claude 配置', 'anthropic')
  await model(page, '手动预算', 'Claude Haiku 4.5')
  await page
    .getByRole('article', { name: '模型方案：手动预算', exact: true })
    .getByRole('button', { name: '高级设置' })
    .click()
  const editor = page.getByRole('dialog', { name: '编辑模型方案', exact: true })
  await editor.locator('[name="reasoning_mode"]').selectOption('budget')
  await editor.locator('[name="budget_tokens"]').fill('1023')
  await editor.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(editor.getByRole('alert')).toContainText('目录范围')
  await editor.locator('[name="budget_tokens"]').fill('16384')
  await editor.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(editor.getByRole('alert')).toContainText('必须小于')
  await editor.locator('[name="budget_tokens"]').fill('4096')
  await editor.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(editor).not.toBeVisible()
  await expect(page.getByRole('article', { name: '模型方案：手动预算' })).toContainText('4,096')
})

test('上游鉴权测试失败保留登录，更换密钥后可重新测试并设为默认', async ({ page, account }) => {
  await login(page, account)
  await page.goto('/models')
  await provider(page, '密钥测试', 'deepseek', 'e2e-rejected-key')
  await model(page)
  const card = page.getByRole('article', { name: '模型方案：日常问答' })
  await card.getByRole('button', { name: '测试', exact: true }).click()
  await expect(card).toContainText('鉴权失败')
  await expect(page).toHaveURL(/\/models$/)
  await page.getByRole('button', { name: '编辑供应商', exact: true }).click()
  const editor = page.getByRole('dialog', { name: '编辑供应商配置', exact: true })
  await editor.locator('[name="api_key"]').fill('e2e-updated-key')
  await editor.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(editor).not.toBeVisible()
  await card.getByRole('button', { name: '测试', exact: true }).click()
  await expect(card).toContainText('文本流通过')
  await card.getByRole('button', { name: '高级设置', exact: true }).click()
  const modelEditor = page.getByRole('dialog', { name: '编辑模型方案' })
  await modelEditor.locator('[name="max_output_tokens"]').fill('20000')
  await modelEditor.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(modelEditor).not.toBeVisible()
  await expect(card).toContainText('配置已修改，请重新测试')
  await card.getByRole('button', { name: '设为默认', exact: true }).click()
  await expect(
    page.getByRole('article', { name: '模型方案：日常问答', exact: true }),
  ).toContainText('当前默认')
})

test('卡片与居中弹窗支持键盘、草稿保护、焦点恢复及窄屏', async ({ page, account }, testInfo) => {
  await login(page, account)
  await page.goto('/models')
  const trigger = page.getByRole('button', { name: '配置 DeepSeek', exact: true })
  await trigger.focus()
  await page.keyboard.press('Enter')
  const dialog = page.getByRole('dialog', { name: 'DeepSeek', exact: true })
  const add = dialog.getByRole('button', { name: '添加首个供应商连接', exact: true })
  await add.click()
  const editor = page.getByRole('dialog', { name: '添加供应商配置', exact: true })
  await editor.locator('[name="name"]').fill('未保存的连接')
  await page.keyboard.press('Tab')
  await expect
    .poll(() => editor.evaluate((element) => element.contains(document.activeElement)))
    .toBe(true)
  await page.screenshot({ path: testInfo.outputPath('configuration-modal.png'), fullPage: true })
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog', { name: '放弃未保存的更改？', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '继续编辑', exact: true }).click()
  await expect(editor.locator('[name="name"]')).toHaveValue('未保存的连接')
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: '放弃更改', exact: true }).click()
  await expect(editor).not.toBeVisible()
  await expect(dialog).toBeVisible()
  await expect(add).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(dialog).not.toBeVisible()
  await expect(trigger).toBeFocused()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

// 以实际布局和滚动行为验收左右分区，截图用于检查 Windows 滚动条周围的圆角。
test('供应商弹窗左右分区独立滚动，窄屏上下排列且保留完整圆角', async ({
  page,
  account,
}, testInfo) => {
  await login(page, account)
  await page.goto('/models')
  await provider(page, '布局验收连接', 'anthropic')
  const dialog = page.getByRole('dialog', { name: 'Anthropic', exact: true })
  const left = page.getByRole('region', { name: '供应商连接', exact: true })
  const right = page.getByRole('region', { name: '关联模型方案', exact: true })
  await expect(right.getByRole('article')).toHaveCount(6)
  const leftBox = await left.boundingBox(),
    rightBox = await right.boundingBox()
  const corners = await dialog.evaluate((element) => {
    const style = getComputedStyle(element)
    return {
      top: parseFloat(style.borderTopRightRadius),
      bottom: parseFloat(style.borderBottomRightRadius),
      fits: element.scrollHeight <= element.clientHeight + 1,
    }
  })
  expect(corners.top).toBeGreaterThan(0)
  expect(corners.bottom).toBeGreaterThan(0)
  expect(corners.fits).toBe(true)
  if (testInfo.project.name === 'model-config-desktop') {
    expect(leftBox!.x + leftBox!.width).toBeLessThanOrEqual(rightBox!.x)
    await right.hover()
    await page.mouse.wheel(0, 1200)
    await expect.poll(() => right.evaluate((element) => element.scrollTop)).toBeGreaterThan(0)
    await expect(left.getByRole('heading', { name: /^供应商连接/ })).toBeVisible()
  } else expect(leftBox!.y + leftBox!.height).toBeLessThanOrEqual(rightBox!.y)
  await expect(dialog.getByRole('button', { name: '关闭', exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('provider-split-layout.png'), fullPage: true })
})

// 多连接通过卡片选择；草稿确认、非当前连接启停与默认引用均走真实接口。
test('连接卡片切换、独立启停和草稿保护，模型底栏操作直接可见', async ({
  page,
  account,
}, testInfo) => {
  await login(page, account)
  await page.goto('/models')
  await provider(page, '主账号')
  await model(page, '主账号模型')
  const primary = page.getByRole('article', { name: '供应商连接：主账号', exact: true })
  await provider(page, '备用账号')
  const secondary = page.getByRole('article', { name: '供应商连接：备用账号', exact: true })
  await expect(page.locator('.provider-connection-card')).toHaveCount(2)
  await expect(
    secondary.getByRole('button', { name: '切换连接 备用账号', exact: true }),
  ).toHaveAttribute('aria-pressed', 'true')
  const models = page.getByRole('region', { name: '关联模型方案', exact: true })
  await expect(
    models.getByRole('article', { name: '模型方案：主账号模型', exact: true }),
  ).toHaveCount(0)
  await model(page, '备用账号模型')
  // 不选中主账号也可停用它，不改变右侧当前连接或备用模型的状态。
  await primary.getByRole('switch').click()
  await expect(primary.getByRole('switch')).not.toBeChecked()
  await expect(secondary.getByRole('switch')).toBeChecked()
  await expect(
    models
      .getByRole('article', { name: '模型方案：备用账号模型', exact: true })
      .getByRole('switch'),
  ).toBeChecked()
  const choosePrimary = primary.getByRole('button', { name: '切换连接 主账号', exact: true })
  await choosePrimary.focus()
  await page.keyboard.press('Enter')
  const first = models.getByRole('article', { name: '模型方案：主账号模型', exact: true })
  await expect(first.getByRole('switch')).toBeChecked()
  await expect(first).toContainText('连接已停用')
  await expect(first.getByRole('button', { name: '设为默认', exact: true })).toBeDisabled()
  await primary.getByRole('switch').click()
  await first.getByRole('button', { name: '设为默认', exact: true }).click()
  await expect(first).toContainText('当前默认')
  for (const name of ['高级设置', '测试', '删除', '清除默认'])
    await expect(first.getByRole('button', { name, exact: true })).toBeVisible()
  await expect(page.getByText('更多操作', { exact: true })).toHaveCount(0)
  await primary.getByRole('button', { name: '编辑供应商', exact: true }).click()
  const editor = page.getByRole('dialog', { name: '编辑供应商配置', exact: true })
  await editor.locator('[name="api_key"]').fill('不会写入服务端的草稿')
  const chooseSecondary = secondary.getByRole('button', { name: '切换连接 备用账号', exact: true })
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: '继续编辑', exact: true }).click()
  await expect(editor.locator('[name="api_key"]')).toHaveValue('不会写入服务端的草稿')
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: '放弃更改', exact: true }).click()
  await expect(editor).not.toBeVisible()
  await expect(primary.getByRole('button', { name: '编辑供应商', exact: true })).toBeFocused()
  await chooseSecondary.click()
  await expect(
    models.getByRole('article', { name: '模型方案：备用账号模型', exact: true }),
  ).toBeVisible()
  await choosePrimary.click()
  await expect(first).toContainText('当前默认')
  // 大屏参数与操作并排；手机允许底栏换行，但操作仍在卡片范围内且不横向溢出。
  const summary = await first.locator('.config-model-options').boundingBox()
  const tools = await first.getByRole('group').boundingBox()
  const box = await first.boundingBox()
  if (testInfo.project.name === 'model-config-desktop') {
    expect(tools!.x).toBeGreaterThanOrEqual(summary!.x + summary!.width)
    expect(Math.abs(tools!.y - summary!.y)).toBeLessThan(12)
    const connectionBox = await primary.boundingBox()
    expect(Math.abs(connectionBox!.y - box!.y)).toBeLessThan(3)
  }
  expect(tools!.x + tools!.width).toBeLessThanOrEqual(box!.x + box!.width)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({
    path: testInfo.outputPath('connection-cards-and-model-actions.png'),
    fullPage: true,
  })
  if (testInfo.project.name === 'model-config-narrow') {
    await first.getByRole('group').scrollIntoViewIfNeeded()
    await page.screenshot({ path: testInfo.outputPath('model-actions-narrow.png'), fullPage: true })
  }
})

// 真实浏览器同时检查编辑弹窗的层级、固定底栏、焦点循环和关闭后恢复。
test('连接与模型在居中弹窗编辑，长表单独立滚动且焦点逐层恢复', async ({
  page,
  account,
}, testInfo) => {
  await login(page, account)
  await page.goto('/models')
  await provider(page)
  const editConnection = page.getByRole('button', { name: '编辑供应商', exact: true })
  await editConnection.click()
  const connectionEditor = page.getByRole('dialog', { name: '编辑供应商配置', exact: true })
  await expect(connectionEditor).toBeVisible()
  await expect(
    connectionEditor.getByRole('heading', { name: '连接信息', exact: true }),
  ).toBeVisible()
  await expect(
    connectionEditor.getByRole('heading', { name: '访问凭据', exact: true }),
  ).toBeVisible()
  await expect(connectionEditor.locator('[name="api_key"]')).toHaveValue('')
  const editorBox = await connectionEditor.boundingBox()
  expect(
    Math.abs(editorBox!.x + editorBox!.width / 2 - page.viewportSize()!.width / 2),
  ).toBeLessThan(2)
  // 第二层遮罩必须高于主面板，编辑内容又必须高于自己的遮罩。
  const layers = await page
    .locator('.config-modal')
    .evaluateAll((elements) => elements.map((element) => Number(getComputedStyle(element).zIndex)))
  const overlays = await page
    .locator('.config-modal-overlay')
    .evaluateAll((elements) => elements.map((element) => Number(getComputedStyle(element).zIndex)))
  expect(overlays[1]).toBeGreaterThan(layers[0]!)
  expect(layers[1]).toBeGreaterThan(overlays[1]!)
  await page.screenshot({
    path: testInfo.outputPath('connection-editor-light.png'),
    fullPage: true,
  })
  await page.keyboard.press('Escape')
  await expect(connectionEditor).not.toBeVisible()
  await expect(editConnection).toBeFocused()
  await model(page, '弹窗模型')
  await closeProvider(page)
  // 从真实外观菜单切换主题后复用模型，覆盖居中编辑器的暗色状态。
  const navigationTrigger = page.getByRole('button', { name: '打开侧栏', exact: true })
  if (await navigationTrigger.isVisible()) await navigationTrigger.click()
  await page.getByRole('button', { name: /外观.*浅色/ }).click()
  await page.getByRole('menuitemradio', { name: '深色', exact: true }).click()
  await closeSidebar(page)
  await openProvider(page)
  const row = page.getByRole('article', { name: '模型方案：弹窗模型', exact: true })
  const advanced = row.getByRole('button', { name: '高级设置', exact: true })
  await advanced.click()
  const editor = page.getByRole('dialog', { name: '编辑模型方案', exact: true })
  await expect(editor.locator('[name="catalog_model_id"]')).toHaveCount(0)
  await expect(editor.getByRole('heading', { name: '模型参数', exact: true })).toBeVisible()
  await editor.locator('[name="reasoning_policy"]').selectOption('selectable')
  await editor.locator('[name="allow_off"]').check()
  await page.screenshot({ path: testInfo.outputPath('model-editor-dark.png'), fullPage: true })
  const fields = editor.locator('.config-fields')
  // 底栏的保存按钮始终留在编辑弹窗内，字段较长时仅中间区域滚动。
  const formBox = await fields.boundingBox(),
    footerBox = await editor.locator('footer').boundingBox()
  expect(formBox!.y + formBox!.height).toBeLessThanOrEqual(footerBox!.y + 1)
  await expect(editor.getByRole('button', { name: '保存配置', exact: true })).toBeInViewport()
  await editor.getByRole('button', { name: '保存配置', exact: true }).focus()
  await page.keyboard.press('Tab')
  await expect(editor.getByRole('button', { name: '关闭', exact: true })).toBeFocused()
  await page.keyboard.press('Shift+Tab')
  await expect(editor.getByRole('button', { name: '保存配置', exact: true })).toBeFocused()
  await page.keyboard.press('Escape')
  const confirmation = page.getByRole('dialog', { name: '放弃未保存的更改？', exact: true })
  await expect(confirmation).toBeVisible()
  const lastLayers = await page
    .locator('.config-modal')
    .evaluateAll((elements) => elements.map((element) => Number(getComputedStyle(element).zIndex)))
  expect(lastLayers[2]).toBeGreaterThan(lastLayers[1]!)
  await page.keyboard.press('Escape')
  await expect(confirmation).not.toBeVisible()
  await expect(editor.locator('[name="reasoning_policy"]')).toHaveValue('selectable')
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: '放弃更改', exact: true }).click()
  await expect(editor).not.toBeVisible()
  await expect(advanced).toBeFocused()
  await expect(row).toContainText('弹窗模型')
})

// 自动清除默认与删除模型为顺序请求；服务端历史引用仍保留并显示已删除状态。
test('默认模型确认删除后自动清除默认并保留既有聊天历史', async ({ page, account, request }) => {
  await login(page, account)
  await page.goto('/models')
  await provider(page)
  await model(page, '即将删除的默认')
  const row = page.getByRole('article', { name: '模型方案：即将删除的默认', exact: true })
  await row.getByRole('button', { name: '设为默认', exact: true }).click()
  await closeProvider(page)
  await returnToChat(page)
  await send(page, '删除模型仍保留的历史')
  await finished(page)
  await openPicker(page)
  await page.getByRole('link', { name: '前往模型管理', exact: true }).click()
  await openProvider(page)
  await row.getByRole('button', { name: '删除', exact: true }).click()
  await page.getByRole('button', { name: '确认删除', exact: true }).click()
  await expect(row).toHaveCount(0)
  const auth = await headers(request, account)
  const selected = await (
    await request.get(control().url + '/api/model-config/default', { headers: auth })
  ).json()
  expect(selected.data.model_configuration_id).toBeNull()
  await closeProvider(page)
  await returnToChat(page)
  await expect(page.getByRole('region', { name: '聊天模型状态' })).toContainText('原模型方案已删除')
  await expect(await finished(page)).toContainText('删除模型仍保留的历史')
  await expect(page.getByRole('button', { name: '发送消息', exact: true })).toBeDisabled()
})
