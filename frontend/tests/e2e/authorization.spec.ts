import { selectOption } from '../support/playwright/controls'
/** 权限管理真实流程：独立账号与临时库验证组织、成员、角色、凭据和前端权限回收。 */
import { randomUUID } from 'node:crypto'
import type { Page } from '@playwright/test'
import { test, apiUrl, identity, grantAdmin } from '../support/playwright/authorization'
import {
  accountAppearance,
  test as ordinaryTest,
  expect,
  login,
  sidebar,
  closeSidebar,
  createAccount,
} from '../support/playwright/fixtures'

/** 从公共导航进入组织工作台，窄屏同时验证抽屉关闭。 */
async function openOrganization(page: Page): Promise<void> {
  await (await sidebar(page)).getByRole('link', { name: '组织与权限', exact: true }).click()
  await expect(page.getByRole('heading', { name: '组织与权限', exact: true })).toBeVisible()
  await expect(page.getByRole('region', { name: '管理范围' })).toContainText('当前管理范围')
  await expect(page.getByText('管理权限不包含他人的个人会话。', { exact: true })).toBeVisible()
  await expect(page.getByText('聚人成舟', { exact: false })).toHaveCount(0)
}

/** 提交当前操作弹窗，使用可访问名称避免与背景行按钮混淆。 */
async function confirm(
  page: Page,
  title: string,
  button: string,
  field?: { label: string; value: string },
): Promise<void> {
  const dialog = page.getByRole('dialog', { name: title, exact: true })
  await expect(dialog).toBeVisible()
  if (field) await dialog.getByLabel(field.label, { exact: true }).fill(field.value)
  await dialog.getByRole('button', { name: button, exact: true }).click()
  await expect(dialog).not.toBeVisible()
}

ordinaryTest('普通账号隐藏所有管理入口，直接打开管理地址仍回到聊天', async ({ page, account }) => {
  await login(page, account)
  const navigation = await sidebar(page)
  await expect(navigation.getByRole('link', { name: '组织与权限' })).toHaveCount(0)
  await expect(navigation.getByRole('link', { name: '模型管理' })).toHaveCount(0)
  await closeSidebar(page)
  await page.goto('/organization')
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('textbox', { name: '消息内容' })).toBeVisible()
  await page.goto('/models')
  await expect(page).toHaveURL(/\/$/)
  await page.getByRole('button', { name: '选择聊天模型' }).click()
  await expect(page.getByRole('link', { name: '前往模型管理' })).toHaveCount(0)
})

test('创建与改名部门，加入成员、授予和撤销部门管理员，最后移出并删除', async ({
  page,
  account,
  request,
}, testInfo) => {
  const member = await createAccount(request),
    name = `山海_${randomUUID().slice(0, 8)}`
  await login(page, account)
  await openOrganization(page)
  await page.getByRole('button', { name: '新建部门', exact: true }).click()
  const createDialog = page.getByRole('dialog', { name: '新建部门', exact: true })
  await createDialog.getByLabel('部门名称', { exact: true }).focus()
  expect(
    await createDialog
      .getByLabel('部门名称', { exact: true })
      .evaluate((element) => getComputedStyle(element).outlineStyle),
  ).toBe('none')
  await createDialog.screenshot({ path: testInfo.outputPath('department-input-focus.png') })
  await confirm(page, '新建部门', '创建部门', { label: '部门名称', value: name })
  await expect(page.locator('.operation-notice')).toHaveCount(0)
  await page
    .getByRole('navigation', { name: '选择部门' })
    .getByRole('button', { name, exact: true })
    .click()
  await page.getByRole('button', { name: '加入成员', exact: true }).click()
  await confirm(page, '加入成员', '加入部门', { label: '完整用户名', value: member.username })
  let row = page.getByRole('listitem').filter({ hasText: member.username })
  await expect(row).toBeVisible()
  await row.getByRole('button', { name: '设为管理员', exact: true }).click()
  await confirm(page, '设为部门管理员', '授予权限')
  row = page.getByRole('listitem').filter({ hasText: member.username })
  await expect(row).toContainText('部门管理员')
  await page.screenshot({ path: testInfo.outputPath('organization-light.png'), fullPage: true })
  await accountAppearance(page)
  await page.getByRole('menuitemradio', { name: '深色', exact: true }).click()
  await closeSidebar(page)
  await page.screenshot({ path: testInfo.outputPath('organization-dark.png'), fullPage: true })
  expect(
    await page
      .locator('.organization-scroll')
      .evaluate((element) => element.scrollWidth <= element.clientWidth),
  ).toBe(true)
  await page.getByRole('button', { name: '重命名', exact: true }).click()
  await confirm(page, '重命名部门', '保存名称', { label: '部门名称', value: `${name}_新` })
  await expect(page.getByRole('heading', { name: `${name}_新`, exact: true })).toBeVisible()
  await row.getByRole('button', { name: '撤销管理员', exact: true }).click()
  await confirm(page, '撤销部门管理员', '撤销权限')
  await expect(row).toContainText('部门成员')
  await row.getByRole('button', { name: '移出部门', exact: true }).click()
  await confirm(page, '移出部门', '移出部门')
  await expect(row).toHaveCount(0)
  await page.getByRole('button', { name: '删除部门', exact: true }).click()
  await confirm(page, '删除部门', '删除部门')
  await expect(
    page
      .getByRole('navigation', { name: '选择部门' })
      .getByRole('button', { name: `${name}_新`, exact: true }),
  ).toHaveCount(0)
})

test('账号搜索、超管授予撤销、停启与改密使旧令牌失效', async ({
  page,
  account,
  request,
}, testInfo) => {
  const target = await createAccount(request),
    previous = await identity(request, target)
  const administrator = await identity(request, account)
  const created = await request.post(`${apiUrl()}/api/departments`, {
    headers: administrator.headers,
    data: { name: `账号_${randomUUID().slice(0, 8)}` },
  })
  expect(created.ok()).toBe(true)
  const department = (await created.json()).data
  expect(
    (
      await request.post(`${apiUrl()}/api/departments/${department.id}/members`, {
        headers: administrator.headers,
        data: { username: target.username },
      })
    ).ok(),
  ).toBe(true)
  await login(page, account)
  await openOrganization(page)
  await page.getByRole('button', { name: '全站账号', exact: true }).click()
  const activeFilter = page.getByRole('combobox', { name: '账号状态', exact: true })
  await activeFilter.click()
  await expect(page.getByRole('option', { name: '全部状态', exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('account-dropdown.png') })
  await page.keyboard.press('Escape')
  await page.getByRole('checkbox', { name: '仅无部门', exact: true }).hover()
  await expect(page.getByRole('checkbox', { name: '仅无部门', exact: true })).toHaveCSS(
    'cursor',
    'pointer',
  )
  await page.getByRole('searchbox', { name: '搜索账号用户名' }).fill(target.username)
  await selectOption(
    page,
    page.getByRole('combobox', { name: '所属部门', exact: true }),
    department.id,
  )
  await page.getByRole('button', { name: '筛选', exact: true }).click()
  const row = page.getByRole('listitem').filter({ hasText: target.username })
  await row.getByRole('button', { name: '授予超管', exact: true }).click()
  await confirm(page, '授予超级管理员', '授予权限')
  await expect(row).toContainText('超级管理员')
  await row.getByRole('button', { name: '撤销超管', exact: true }).click()
  await confirm(page, '撤销超级管理员', '撤销权限')
  await row.getByRole('button', { name: '停用', exact: true }).click()
  await confirm(page, '停用账号', '停用账号')
  await expect(row).toContainText('已停用')
  // 另一个独立浏览器会话通过真实登录页验证停用原因，不替换后端或缓存身份。
  const visitor = await page
    .context()
    .browser()!
    .newContext({ baseURL: new URL(page.url()).origin })
  try {
    const loginPage = await visitor.newPage()
    await loginPage.goto('/login')
    await loginPage.getByLabel('用户名', { exact: true }).fill(target.username)
    await loginPage.getByLabel('密码', { exact: true }).fill(target.password)
    await loginPage.getByRole('button', { name: '登录知舟', exact: true }).click()
    await expect(loginPage.getByRole('alert')).toHaveText('账号已被停用，请联系管理员')
    await loginPage.screenshot({ path: testInfo.outputPath('disabled-account.png') })
    await loginPage.getByLabel('密码', { exact: true }).fill('wrong-password')
    await loginPage.getByRole('button', { name: '登录知舟', exact: true }).click()
    await expect(loginPage.getByRole('alert')).toHaveText('用户名或密码错误')
  } finally {
    await visitor.close()
  }
  expect(
    (await request.get(`${apiUrl()}/api/auth/me`, { headers: previous.headers })).status(),
  ).toBe(401)
  await row.getByRole('button', { name: '启用', exact: true }).click()
  await confirm(page, '启用账号', '启用账号')
  const enabled = await identity(request, target)
  await row.getByRole('button', { name: '重置密码', exact: true }).click()
  await confirm(page, '重置密码', '重置密码', { label: '新密码', value: ' new-e2e-password ' })
  expect(
    (await request.get(`${apiUrl()}/api/auth/me`, { headers: enabled.headers })).status(),
  ).toBe(401)
  await identity(request, { ...target, password: ' new-e2e-password ' })
})

// 同一账号登录后被管理端停用，刷新和业务请求都必须带明确原因返回登录页。
for (const trigger of ['刷新恢复', '业务请求'] as const) {
  test(`已登录账号被停用后通过${trigger}显示具体原因`, async ({ page, account, request }) => {
    const target = await createAccount(request)
    const administrator = await identity(request, account)
    await login(page, target)
    await expect(page.getByRole('button', { name: '发送消息', exact: true })).toBeDisabled()
    const current = await identity(request, target)
    const disabled = await request.put(`${apiUrl()}/api/users/${current.user.id}/active`, {
      headers: administrator.headers,
      data: { is_active: false },
    })
    expect(disabled.ok()).toBe(true)
    if (trigger === '刷新恢复') await page.reload()
    else {
      await page.getByRole('textbox', { name: '消息内容', exact: true }).fill('停用后尝试发送')
      await page.getByRole('button', { name: '发送消息', exact: true }).click()
    }
    await expect(page).toHaveURL(/\/login/)
    await expect(page.getByRole('alert')).toHaveText('账号已被停用，请联系管理员')
    await expect(page.getByRole('textbox', { name: '消息内容' })).toHaveCount(0)
  })
}

test('部门管理员仅管理本部门，按用户名加入成员并移出本人后回收入口', async ({
  page,
  account,
  request,
}) => {
  const operator = await createAccount(request),
    another = await createAccount(request)
  const admin = await identity(request, account),
    own = await identity(request, operator)
  const result = await request.post(`${apiUrl()}/api/departments`, {
    headers: admin.headers,
    data: { name: `行舟_${randomUUID().slice(0, 8)}` },
  })
  expect(result.ok()).toBe(true)
  const department = (await result.json()).data
  expect(
    (
      await request.post(`${apiUrl()}/api/departments/${department.id}/members`, {
        headers: admin.headers,
        data: { username: operator.username },
      })
    ).ok(),
  ).toBe(true)
  expect(
    (
      await request.put(
        `${apiUrl()}/api/departments/${department.id}/administrators/${own.user.id}`,
        { headers: admin.headers },
      )
    ).ok(),
  ).toBe(true)
  await login(page, operator)
  await openOrganization(page)
  await expect(page.getByRole('navigation', { name: '选择部门' }).getByRole('button')).toHaveCount(
    1,
  )
  await expect(page.getByRole('button', { name: '全站账号', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '新建部门', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: '加入成员', exact: true }).click()
  await confirm(page, '加入成员', '加入部门', { label: '完整用户名', value: another.username })
  await expect(page.getByRole('listitem').filter({ hasText: another.username })).toBeVisible()
  const self = page.getByRole('listitem').filter({ hasText: operator.username })
  await self.getByRole('button', { name: '移出部门', exact: true }).click()
  await confirm(page, '移出部门', '移出部门')
  await expect(page).toHaveURL(/\/$/)
  await expect((await sidebar(page)).getByRole('link', { name: '组织与权限' })).toHaveCount(0)
})

test('超管降为部门管理员后关闭失权表单，保留本部门工作台且不重放写入', async ({
  page,
  account,
  request,
}) => {
  const other = await createAccount(request)
  await grantAdmin(request, other)
  const operator = await identity(request, account),
    administrator = await identity(request, other)
  const created = await request.post(`${apiUrl()}/api/departments`, {
    headers: administrator.headers,
    data: { name: `归舟_${randomUUID().slice(0, 8)}` },
  })
  expect(created.ok()).toBe(true)
  const department = (await created.json()).data
  expect(
    (
      await request.post(`${apiUrl()}/api/departments/${department.id}/members`, {
        headers: administrator.headers,
        data: { username: account.username },
      })
    ).ok(),
  ).toBe(true)
  expect(
    (
      await request.put(
        `${apiUrl()}/api/departments/${department.id}/administrators/${operator.user.id}`,
        { headers: administrator.headers },
      )
    ).ok(),
  ).toBe(true)
  await login(page, account)
  await openOrganization(page)
  await page.getByRole('button', { name: '全站账号', exact: true }).click()
  await page.getByRole('searchbox', { name: '搜索账号用户名' }).fill(account.username)
  await page.getByRole('button', { name: '筛选', exact: true }).click()
  await page
    .getByRole('listitem')
    .filter({ hasText: account.username })
    .getByRole('button', { name: '重置密码', exact: true })
    .click()
  const dialog = page.getByRole('dialog', { name: '重置密码', exact: true })
  await dialog.getByLabel('新密码', { exact: true }).fill('unsubmitted-password')
  expect(
    (
      await request.delete(`${apiUrl()}/api/users/${operator.user.id}/super-admin`, {
        headers: administrator.headers,
      })
    ).ok(),
  ).toBe(true)
  const writes: string[] = []
  // 只统计当前浏览器对改密接口的实际提交，确认 403 后不会自动重放。
  page.on('request', (event) => {
    if (event.url().endsWith(`/api/users/${operator.user.id}/password`)) writes.push(event.method())
  })
  await dialog.getByRole('button', { name: '重置密码', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  await expect(page).toHaveURL(/\/organization$/)
  await expect(page.getByRole('heading', { name: department.name, exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '全站账号', exact: true })).toHaveCount(0)
  expect(writes).toEqual(['PUT'])
})

test('权限同步断网后暂停管理，重试校验可恢复新授权且不重放失败操作', async ({
  page,
  account,
  request,
}) => {
  const other = await createAccount(request)
  await grantAdmin(request, other)
  const administrator = await identity(request, other),
    operator = await identity(request, account)
  await login(page, account)
  await openOrganization(page)
  await page.getByRole('button', { name: '新建部门', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '新建部门', exact: true })
  await dialog.getByLabel('部门名称', { exact: true }).fill(`未提交_${randomUUID().slice(0, 8)}`)
  expect(
    (
      await request.delete(`${apiUrl()}/api/users/${operator.user.id}/super-admin`, {
        headers: administrator.headers,
      })
    ).ok(),
  ).toBe(true)
  // 只注入一次身份同步服务故障，原操作的 403 与后续恢复仍经过真实后端。
  await page.route(
    '**/api/auth/me',
    async (route) => {
      await route.fulfill({
        status: 503,
        json: { code: 50000, message: '身份校验暂不可用', data: null },
      })
    },
    { times: 1 },
  )
  const writes: string[] = []
  // 验证失败创建仅发送一次，恢复权限不会自动提交之前的部门草稿。
  page.on('request', (event) => {
    if (event.url().endsWith('/api/departments') && event.method() === 'POST')
      writes.push(event.method())
  })
  await dialog.getByRole('button', { name: '创建部门', exact: true }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('button', { name: '重试权限校验', exact: true })).toBeVisible()
  await grantAdmin(request, account)
  await page.getByRole('button', { name: '重试权限校验', exact: true }).click()
  await expect(page.getByRole('button', { name: '重试权限校验', exact: true })).toHaveCount(0)
  await expect(
    (await sidebar(page)).getByRole('link', { name: '组织与权限', exact: true }),
  ).toBeVisible()
  expect(writes).toEqual(['POST'])
})
