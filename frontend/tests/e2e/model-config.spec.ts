/** 模型管理全链路：真实页面与随机库，配置重置及 HTTP 辅助由共用 fixture 负责。 */
import { test, control, provider, model, headers } from '../support/playwright/model-config'
import { expect, login, send, finished } from '../support/playwright/fixtures'

test('首次配置、主动测试、设默认后返回聊天保留草稿，刷新仍可使用', async ({
  page,
  account,
}, testInfo) => {
  await login(page, account)
  await page.getByRole('textbox', { name: '消息内容' }).fill('配置前的草稿')
  await expect(page.getByRole('button', { name: '发送消息', exact: true })).toBeDisabled()
  await page.getByRole('link', { name: '前往模型管理', exact: true }).click()
  await expect(page.getByRole('heading', { name: '从一份供应商配置开始' })).toBeVisible()
  // 大屏与手机分别留图，验证首次空状态及新增供应商后的真实比例，不维护像素基线。
  if (testInfo.project.name === 'model-config-desktop')
    await page.setViewportSize({ width: 1920, height: 945 })
  await page.screenshot({ path: testInfo.outputPath('empty-state.png'), fullPage: true })
  await provider(page)
  await expect(page.getByRole('region', { name: '关联模型方案' })).toContainText('我的 DeepSeek')
  await expect(page.getByRole('heading', { name: '为这份连接添加第一个模型' })).toBeVisible()
  await expect(page.getByRole('region', { name: '全局默认模型' })).toContainText('还没有默认模型')
  const defaultBox = await page.getByRole('region', { name: '全局默认模型' }).boundingBox()
  expect(defaultBox!.height).toBeLessThan(
    testInfo.project.name === 'model-config-desktop' ? 130 : 220,
  )
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    .toBe(true)
  await page.screenshot({ path: testInfo.outputPath('provider-added.png'), fullPage: true })
  await model(page)
  const card = page.getByRole('article', { name: '模型方案：日常问答', exact: true })
  await expect(card).toContainText('尚未测试')
  await page.screenshot({ path: testInfo.outputPath('model-ready.png'), fullPage: true })
  await card.getByRole('button', { name: '设为默认', exact: true }).click()
  await expect(page.getByRole('region', { name: '全局默认模型' })).toContainText('日常问答')
  await card.getByRole('button', { name: '测试', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('可能产生供应商费用')
  await page.getByRole('button', { name: '开始测试', exact: true }).click()
  await expect(card).toContainText('文本流通过')
  await page.getByRole('link', { name: '返回聊天', exact: true }).last().click()
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
  await expect(page.getByRole('dialog')).toContainText('不能直接删除')
  await page.getByRole('button', { name: '知道了', exact: true }).click()
  await page.getByRole('button', { name: '删除供应商', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('仍被引用')
  await page.getByRole('button', { name: '知道了', exact: true }).click()
  await model(page, '深入思考')
  const second = page.getByRole('article', { name: '模型方案：深入思考', exact: true })
  await second.getByRole('button', { name: '编辑', exact: true }).click()
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
  await page.getByRole('button', { name: '清除默认', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('所有用户')
  await page.getByRole('dialog').getByRole('button', { name: '清除默认', exact: true }).click()
  await expect(page.getByRole('region', { name: '全局默认模型' })).toContainText('还没有默认模型')
  await second.getByRole('button', { name: '删除', exact: true }).click()
  await page.getByRole('button', { name: '确认删除', exact: true }).click()
  await expect(second).toHaveCount(0)
  await page.getByRole('button', { name: '删除供应商', exact: true }).click()
  await page.getByRole('button', { name: '确认删除', exact: true }).click()
  await expect(page.getByRole('heading', { name: '从一份供应商配置开始' })).toBeVisible()
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
  await expect(page.getByRole('region', { name: '全局默认模型' })).toContainText('日常问答')
  await page.getByRole('link', { name: '返回聊天', exact: true }).click()
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
  await page.getByRole('button', { name: '刷新模型选项', exact: true }).click()
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
  await page.getByRole('button', { name: '添加', exact: true }).click()
  const editor = page.getByRole('dialog', { name: '添加供应商配置', exact: true })
  await editor.locator('[name="provider"]').selectOption('bailian')
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
  await expect(page.getByRole('region', { name: '关联模型方案' })).toContainText(address)
  await model(page, '百炼日常问答')
  const card = page.getByRole('article', { name: '模型方案：百炼日常问答', exact: true })
  await card.getByRole('button', { name: '设为默认', exact: true }).click()
  await card.getByRole('button', { name: '测试', exact: true }).click()
  await page.getByRole('button', { name: '开始测试', exact: true }).click()
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
  await expect(page.getByRole('region', { name: '关联模型方案' })).toContainText(changed)
  await expect(card).toContainText('配置已修改，请重新测试')
  await page.getByRole('link', { name: '返回聊天', exact: true }).click()
  await send(page, '使用百炼地址配置聊天')
  await finished(page)
  await page.reload()
  await page.goto('/models')
  await expect(page.getByRole('region', { name: '关联模型方案' })).toContainText(changed)
  await expect(page.getByRole('region', { name: '全局默认模型' })).toContainText('百炼日常问答')
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
  await editor.getByRole('button', { name: '读取最新版本，重新编辑', exact: true }).click()
  await expect(editor.locator('[name="name"]')).toHaveValue('远端修改名称')
  await editor.locator('[name="name"]').fill('基于新版本保存')
  await editor.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(editor).not.toBeVisible()
  await expect(page.getByRole('region', { name: '关联模型方案' })).toContainText('基于新版本保存')
})

test('目录推理预算与输出约束即时提示，正确参数才能保存', async ({ page, account }) => {
  await login(page, account)
  await page.goto('/models')
  await provider(page, 'Claude 配置', 'anthropic')
  await page.getByRole('button', { name: '添加模型方案', exact: true }).click()
  const editor = page.getByRole('dialog', { name: '添加模型方案', exact: true })
  await editor.locator('[name="name"]').fill('手动预算')
  await editor
    .locator('[name="catalog_model_id"]')
    .selectOption('anthropic:claude-haiku-4-5-20251001')
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
  await page.getByRole('button', { name: '开始测试', exact: true }).click()
  await expect(card).toContainText('鉴权失败')
  await expect(page).toHaveURL(/\/models$/)
  await page.getByRole('button', { name: '编辑供应商', exact: true }).click()
  const editor = page.getByRole('dialog', { name: '编辑供应商配置', exact: true })
  await editor.locator('[name="api_key"]').fill('e2e-updated-key')
  await editor.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(editor).not.toBeVisible()
  await card.getByRole('button', { name: '测试', exact: true }).click()
  await page.getByRole('button', { name: '开始测试', exact: true }).click()
  await expect(card).toContainText('文本流通过')
  await card.getByRole('button', { name: '编辑', exact: true }).click()
  const modelEditor = page.getByRole('dialog', { name: '编辑模型方案' })
  await modelEditor.locator('[name="max_output_tokens"]').fill('20000')
  await modelEditor.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(modelEditor).not.toBeVisible()
  await expect(card).toContainText('配置已修改，请重新测试')
  await card.getByRole('button', { name: '设为默认', exact: true }).click()
  await expect(page.getByRole('region', { name: '全局默认模型' })).toContainText('日常问答')
})

test('有未保存输入时关闭和离页都可取消，窄屏抽屉保留键盘操作', async ({
  page,
  account,
}, testInfo) => {
  await login(page, account)
  await page.goto('/models')
  await page.getByRole('button', { name: '添加', exact: true }).click()
  const editor = page.getByRole('dialog', { name: '添加供应商配置', exact: true })
  await editor.locator('[name="name"]').fill('未保存的连接')
  await page.screenshot({ path: testInfo.outputPath('configuration-drawer.png'), fullPage: true })
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog', { name: '放弃未保存的更改？', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '继续编辑', exact: true }).click()
  await expect(editor.locator('[name="name"]')).toHaveValue('未保存的连接')
  await editor.getByRole('button', { name: '取消', exact: true }).click()
  await page.getByRole('button', { name: '放弃更改', exact: true }).click()
  await expect(editor).not.toBeVisible()
  await expect(page.getByRole('button', { name: '添加', exact: true })).toBeFocused()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})
