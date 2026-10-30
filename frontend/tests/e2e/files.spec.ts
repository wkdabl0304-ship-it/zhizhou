/** 资料库真实后端验收：桌面和窄屏验证上传下载、目录、版本冲突、权限与策略。 */
import { readFile } from 'node:fs/promises'
import { randomUUID } from 'node:crypto'
import { test, expect, login, sidebar, closeSidebar } from '../support/playwright/fixtures'
import { apiUrl, grantAdmin, identity } from '../support/playwright/authorization'
import type { Locator, Page } from '@playwright/test'
import { selectOption } from '../support/playwright/controls'

/** 通过工作区侧栏进入资料库，窄屏等待抽屉关闭。 */
async function openFiles(page: Page): Promise<void> {
  await (await sidebar(page)).getByRole('link', { name: '资料库', exact: true }).click()
  await expect(page.getByRole('heading', { level: 1, name: '资料库', exact: true })).toBeVisible()
  await closeSidebar(page)
  await expect(page.getByRole('button', { name: '上传文件', exact: true })).toBeVisible()
}

/** 使用可见弹窗创建目录，等待写入与目录重读完成。 */
async function createFolder(page: Page, name: string): Promise<void> {
  await page.getByRole('button', { name: '新建文件夹', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '新建文件夹', exact: true })
  const input = dialog.getByLabel('名称', { exact: true })
  await expect(input).toBeFocused()
  await input.fill(name)
  await input.press('Enter')
  await expect(dialog).not.toBeVisible()
  await expect(page.getByRole('button', { name, exact: true })).toBeVisible()
}

/** 读取实际 SVG 造型和绘制色，验证切换主题时填充、分类色和标签均保持一致。 */
async function iconAppearance(icon: Locator) {
  return icon.evaluate((element) => ({
    markup: element.innerHTML,
    paper: getComputedStyle(element.querySelector('.file-icon-paper, .file-folder-paper')!).fill,
    shapes: Array.from(element.querySelectorAll('path, rect, text, circle, ellipse')).map(
      (shape) => {
        const style = getComputedStyle(shape)
        return {
          fill: style.fill,
          stroke: style.stroke,
          opacity: style.opacity,
          transform: style.transform,
        }
      },
    ),
  }))
}

test('个人资料完整流程：目录、同名另存、原件下载、重命名和递归删除', async ({
  page,
  account,
}, testInfo) => {
  await login(page, account)
  await openFiles(page)
  await expect(page.locator('.files-hero')).toHaveCount(0)
  await expect(page.getByText('上传文件或拖入此目录', { exact: true })).toBeVisible()
  await expect(page.locator('.file-footnote')).toContainText('单文件上限')
  await expect(page.getByRole('complementary', { name: '资料空间' })).toContainText('仅自己可见')
  await createFolder(page, '项目手记')
  await page.getByRole('button', { name: '项目手记', exact: true }).click()
  await expect(page).toHaveURL(/folder=/)
  const content = Buffer.from('山海之间，知舟同行。\n')
  const upload = { name: '山海手记.txt', mimeType: 'text/plain', buffer: content }
  await page.getByLabel('选择上传文件', { exact: true }).setInputFiles(upload)
  await expect(page.getByRole('button', { name: '下载 山海手记.txt', exact: true })).toBeVisible()
  await page.getByLabel('选择上传文件', { exact: true }).setInputFiles(upload)
  await expect(
    page.getByRole('button', { name: '下载 山海手记 (1).txt', exact: true }),
  ).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('files-light.png'), fullPage: true })
  const downloaded = page.waitForEvent('download')
  await page.getByRole('button', { name: '下载 山海手记.txt', exact: true }).click()
  const attachment = await downloaded
  expect(attachment.suggestedFilename()).toBe('山海手记.txt')
  expect(await readFile((await attachment.path())!)).toEqual(content)
  await page.getByRole('button', { name: '重命名 山海手记.txt', exact: true }).click()
  const rename = page.getByRole('dialog', { name: '重命名', exact: true })
  await rename.getByLabel('名称', { exact: true }).fill('归档手记.txt')
  await rename.getByRole('button', { name: '保存名称', exact: true }).click()
  await expect(rename).not.toBeVisible()
  await expect(page.getByRole('button', { name: '下载 归档手记.txt', exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('button', { name: '下载 归档手记.txt', exact: true })).toBeVisible()
  const nav = await sidebar(page)
  await nav.getByRole('button', { name: /外观.*浅色/ }).click()
  await page.getByRole('menuitemradio', { name: '深色', exact: true }).click()
  await closeSidebar(page)
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await page.screenshot({ path: testInfo.outputPath('files-dark.png'), fullPage: true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.getByRole('button', { name: '上一级', exact: true }).click()
  await expect(page).not.toHaveURL(/folder=/)
  await page.getByRole('button', { name: '删除 项目手记', exact: true }).click()
  const deletion = page.getByRole('dialog', { name: '删除资料', exact: true })
  await expect(deletion).toContainText('所有下级资料将一并删除')
  await expect(deletion.getByRole('button', { name: '取消', exact: true })).toBeFocused()
  await deletion.getByRole('button', { name: '取消', exact: true }).click()
  await expect(page.getByRole('button', { name: '项目手记', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '删除 项目手记', exact: true }).click()
  await deletion.getByRole('button', { name: '确认删除', exact: true }).click()
  await expect(deletion).not.toBeVisible()
  await expect(page.getByRole('button', { name: '项目手记', exact: true })).toHaveCount(0)
  await page.reload()
  await expect(page.getByText('暂无文件', { exact: true })).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('普通账号共享空间只读，旧版本重命名保留错误并同步最新内容', async ({
  page,
  account,
  request,
}) => {
  await login(page, account)
  await openFiles(page)
  await page
    .getByRole('navigation', { name: '选择资料空间' })
    .getByRole('button', { name: /全局/ })
    .click()
  await expect(page.getByText(/当前空间可浏览与下载/)).toBeVisible()
  await expect(page.getByRole('button', { name: '上传文件', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '上传上限', exact: true })).toHaveCount(0)
  await page
    .getByRole('navigation', { name: '选择资料空间' })
    .getByRole('button', { name: /个人/ })
    .click()
  await createFolder(page, '并发目录')
  await page.getByRole('button', { name: '重命名 并发目录', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '重命名', exact: true })
  const auth = await identity(request, account)
  const spaceId = new URL(page.url()).searchParams.get('space')!
  const listing = await request.get(`${apiUrl()}/api/files/spaces/${spaceId}/entries`, {
    headers: auth.headers,
  })
  const entry = (await listing.json()).data.items.find(
    (row: { name: string }) => row.name === '并发目录',
  )
  expect(
    (
      await request.patch(`${apiUrl()}/api/files/entries/${entry.id}`, {
        headers: auth.headers,
        data: { name: '另一窗口已改名', version: entry.version },
      })
    ).ok(),
  ).toBe(true)
  await dialog.getByLabel('名称', { exact: true }).fill('本地草稿')
  await dialog.getByRole('button', { name: '保存名称', exact: true }).click()
  await expect(dialog.getByRole('alert')).toContainText('重新查看后再操作')
  await expect(dialog.getByLabel('名称', { exact: true })).toHaveValue('本地草稿')
  await expect(dialog.getByRole('button', { name: '保存名称', exact: true })).toBeDisabled()
  await dialog.getByRole('button', { name: '取消', exact: true }).click()
  await expect(page.getByRole('button', { name: '另一窗口已改名', exact: true })).toBeVisible()
})

test('管理员以数字和单位设置部门上限，重新打开保持小数容量并阻止超限文件', async ({
  page,
  account,
  request,
}, testInfo) => {
  await grantAdmin(request, account)
  const auth = await identity(request, account)
  const created = await request.post(`${apiUrl()}/api/departments`, {
    headers: auth.headers,
    data: { name: `资料测试_${randomUUID().slice(0, 8)}` },
  })
  expect(created.ok()).toBe(true)
  const department = (await created.json()).data
  await login(page, account)
  await openFiles(page)
  await page
    .getByRole('navigation', { name: '选择资料空间' })
    .getByRole('button', { name: new RegExp(department.name) })
    .click()
  await page.getByRole('button', { name: '上传上限', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '单文件上传上限', exact: true })
  await expect(dialog.getByLabel('单文件大小', { exact: true })).toHaveValue('100')
  await expect(dialog.getByRole('combobox', { name: '容量单位', exact: true })).toContainText('MB')
  await selectOption(page, dialog.getByRole('combobox', { name: '容量单位', exact: true }), 'KB')
  await dialog.getByLabel('单文件大小', { exact: true }).fill('1.5')
  await page.screenshot({ path: testInfo.outputPath('files-upload-limit.png'), fullPage: true })
  await dialog.getByRole('button', { name: '保存上限', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  await expect(page.locator('.file-footnote')).toContainText('单文件上限 1.5 KB')
  await page.getByRole('button', { name: '上传上限', exact: true }).click()
  await expect(dialog.getByLabel('单文件大小', { exact: true })).toHaveValue('1.5')
  await expect(dialog.getByRole('combobox', { name: '容量单位', exact: true })).toContainText('KB')
  await selectOption(page, dialog.getByRole('combobox', { name: '容量单位', exact: true }), 'MB')
  await dialog.getByLabel('单文件大小', { exact: true }).fill('1.2')
  await dialog.getByRole('button', { name: '保存上限', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  await page.getByRole('button', { name: '上传上限', exact: true }).click()
  await expect(dialog.getByLabel('单文件大小', { exact: true })).toHaveValue('1.2')
  await expect(dialog.getByRole('combobox', { name: '容量单位', exact: true })).toContainText('MB')
  await selectOption(page, dialog.getByRole('combobox', { name: '容量单位', exact: true }), 'B')
  await dialog.getByLabel('单文件大小', { exact: true }).fill('4')
  await dialog.getByRole('button', { name: '保存上限', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  await expect(page.locator('.file-footnote')).toContainText('单文件上限 4 B')
  await page
    .getByLabel('选择上传文件', { exact: true })
    .setInputFiles({ name: '超限.txt', mimeType: 'text/plain', buffer: Buffer.from('12345') })
  await expect(page.getByRole('alert')).toContainText('超过当前单文件上限 4 B')
  await page
    .getByLabel('选择上传文件', { exact: true })
    .setInputFiles({ name: '空文件.txt', mimeType: 'text/plain', buffer: Buffer.alloc(0) })
  await expect(page.getByRole('button', { name: '下载 空文件.txt', exact: true })).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
})

/** 用浏览器原生 File/DataTransfer 发出外部文件拖放，业务上传仍经过真实后端。 */
async function dropFile(page: Page, target: Locator, name: string): Promise<void> {
  const transfer = await page.evaluateHandle((filename) => {
    const data = new DataTransfer()
    data.items.add(new File(['拖放上传原件'], filename, { type: 'text/plain' }))
    return data
  }, name)
  try {
    await target.dispatchEvent('dragover', { dataTransfer: transfer })
    await expect(page.locator('.file-drop-status')).toBeVisible()
    await target.dispatchEvent('drop', { dataTransfer: transfer })
  } finally {
    await transfer.dispose()
  }
}

test('文件拖入目录空白或文件行留在当前目录，拖到文件夹直接进入并保存到夹内', async ({
  page,
  account,
  request,
}, testInfo) => {
  await login(page, account)
  await openFiles(page)
  await expect(page.getByText('把资料放在这里', { exact: true })).toHaveCount(0)
  await createFolder(page, '收件夹')
  await dropFile(page, page.getByRole('region', { name: '目录内容区', exact: true }), '根目录.txt')
  await expect(page.getByRole('button', { name: '下载 根目录.txt', exact: true })).toBeVisible()
  const fileRow = page
    .getByRole('row')
    .filter({ has: page.getByRole('button', { name: '下载 根目录.txt', exact: true }) })
  await dropFile(page, fileRow, '文件行.txt')
  await expect(page.getByRole('button', { name: '下载 文件行.txt', exact: true })).toBeVisible()
  const folderRow = page
    .getByRole('row')
    .filter({ has: page.getByRole('button', { name: '收件夹', exact: true }) })
  const folderId = await folderRow.getAttribute('data-folder-id')
  await dropFile(page, folderRow, '夹内资料.txt')
  await expect(page).toHaveURL(new RegExp(`folder=${folderId}`))
  await expect(page.getByRole('button', { name: '下载 夹内资料.txt', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '下载 根目录.txt', exact: true })).toHaveCount(0)
  const auth = await identity(request, account)
  const spaceId = new URL(page.url()).searchParams.get('space')!
  const listing = await request.get(
    `${apiUrl()}/api/files/spaces/${spaceId}/entries?parent_id=${folderId}`,
    { headers: auth.headers },
  )
  expect(listing.ok()).toBe(true)
  expect((await listing.json()).data.items).toEqual([
    expect.objectContaining({ name: '夹内资料.txt', parent_id: folderId }),
  ])
  await page.getByRole('button', { name: '上一级', exact: true }).click()
  await expect(page.getByRole('button', { name: '收件夹', exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('files-explorer.png'), fullPage: true })
  const bounds = await page.locator('.file-list-surface').evaluate((element) => {
    const style = getComputedStyle(element)
    const firstCell = element.querySelector('td')!
    const tableStyle = getComputedStyle(firstCell)
    return {
      left: parseFloat(style.paddingLeft),
      right: parseFloat(style.paddingRight),
      cellLeft: parseFloat(tableStyle.paddingLeft),
      cellRight: parseFloat(tableStyle.paddingRight),
    }
  })
  expect(bounds.left).toBeGreaterThanOrEqual(10)
  expect(bounds.right).toBeGreaterThanOrEqual(10)
  expect(bounds.cellLeft).toBeGreaterThanOrEqual(8)
  expect(bounds.cellRight).toBeGreaterThanOrEqual(8)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('单击文件夹整行进入，格式图标随真实目录及重命名同步，明暗主题均可辨认', async ({
  page,
  account,
}, testInfo) => {
  await login(page, account)
  await openFiles(page)
  await expect(page.locator('.files-hero')).toHaveCount(0)
  await expect(page.getByText('上传文件或拖入此目录', { exact: true })).toBeVisible()
  await expect(page.locator('.file-footnote')).toContainText('单文件上限')
  await createFolder(page, '项目资料')
  const folder = page
    .locator('tr[data-folder-id]')
    .filter({ has: page.getByRole('button', { name: '项目资料', exact: true }) })
  await expect(folder).toHaveCSS('cursor', 'pointer')
  const lightFolder = await iconAppearance(folder.locator('.file-type-icon'))
  await folder
    .locator('td')
    .first()
    .click({ position: { x: 8, y: 8 } })
  await expect(page).toHaveURL(/folder=/)
  await page.getByLabel('选择上传文件', { exact: true }).setInputFiles([
    { name: '年度报告.pdf', mimeType: 'application/octet-stream', buffer: Buffer.from('测试原件') },
    {
      name: '项目方案.docx',
      mimeType: 'application/octet-stream',
      buffer: Buffer.from('测试原件'),
    },
    {
      name: '数据报表.xlsx',
      mimeType: 'application/octet-stream',
      buffer: Buffer.from('测试原件'),
    },
    { name: '山水照片.png', mimeType: 'application/octet-stream', buffer: Buffer.from('测试原件') },
    { name: '会议录音.mp3', mimeType: 'application/octet-stream', buffer: Buffer.from('测试原件') },
    { name: '课程视频.mp4', mimeType: 'application/octet-stream', buffer: Buffer.from('测试原件') },
    { name: '归档资料.zip', mimeType: 'application/octet-stream', buffer: Buffer.from('测试原件') },
    { name: '目录代码.ts', mimeType: 'application/octet-stream', buffer: Buffer.from('测试原件') },
  ])
  await expect(page.locator('.file-type-icon')).toHaveCount(8)
  for (const kind of ['pdf', 'word', 'sheet', 'image', 'audio', 'video', 'archive', 'code'])
    await expect(page.locator(`.file-type-icon[data-kind="${kind}"]`)).toBeVisible()
  const pdfIcon = page.locator('.file-type-icon[data-kind="pdf"]')
  const lightPdf = await iconAppearance(pdfIcon)
  expect(lightPdf.paper).toBe('rgb(255, 255, 255)')
  await page.screenshot({ path: testInfo.outputPath('file-types-light.png'), fullPage: true })
  await page.getByRole('button', { name: '重命名 项目方案.docx', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '重命名', exact: true })
  await dialog.getByLabel('名称', { exact: true }).fill('方案摘要.txt')
  await dialog.getByRole('button', { name: '保存名称', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  await expect(page.locator('.file-type-icon[data-kind="word"]')).toHaveCount(0)
  await expect(page.locator('.file-type-icon[data-kind="text"]')).toBeVisible()
  await (await sidebar(page)).getByRole('button', { name: /外观.*浅色/ }).click()
  await page.getByRole('menuitemradio', { name: '深色', exact: true }).click()
  await closeSidebar(page)
  // 深色仍使用同一 SVG 和专用填充色，不能再次回退到透明纸面或另一套图案。
  expect(await iconAppearance(pdfIcon)).toEqual(lightPdf)
  await expect(pdfIcon).toHaveAttribute('aria-label', 'PDF 文档')
  await page.screenshot({ path: testInfo.outputPath('file-types-dark.png'), fullPage: true })
  await page
    .locator('.file-table')
    .screenshot({ path: testInfo.outputPath('file-icons-dark-detail.png') })
  await page.getByRole('button', { name: '上一级', exact: true }).click()
  const folderIcon = page.locator('.file-type-icon[data-kind="folder"]')
  expect(await iconAppearance(folderIcon)).toEqual(lightFolder)
  await page.screenshot({ path: testInfo.outputPath('file-folder-dark.png'), fullPage: true })
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('焦点同步尚未结束时第一次拖入就上传，后台读取仍通过真实后端', async ({ page, account }) => {
  await login(page, account)
  await openFiles(page)
  let release!: () => void
  // 仅延迟一次 GET 的发送，模拟资源管理器返回时较慢的目录同步；不替换业务响应。
  const gate = new Promise<void>((resolve) => {
    release = resolve
  })
  await page.route(
    '**/api/files/spaces/*/entries?**',
    async (route) => {
      await gate
      try {
        await route.continue()
      } catch (failure) {
        if (!route.request().failure()) throw failure
      }
    },
    { times: 1 },
  )
  try {
    const refresh = page.waitForRequest(
      (request) =>
        request.url().includes('/api/files/spaces/') && request.url().includes('/entries?'),
    )
    await page.evaluate(() => window.dispatchEvent(new Event('focus')))
    await refresh
    await expect(page.locator('.file-directory')).toHaveAttribute('aria-busy', 'true')
    const saved = page.waitForResponse(
      (result) => result.request().method() === 'POST' && result.url().endsWith('/files'),
    )
    await dropFile(
      page,
      page.getByRole('region', { name: '目录内容区', exact: true }),
      '第一次就上传.txt',
    )
    expect((await saved).ok()).toBe(true)
    release()
    await expect(
      page.getByRole('button', { name: '下载 第一次就上传.txt', exact: true }),
    ).toBeVisible()
    await expect(page.getByRole('alert')).toHaveCount(0)
  } finally {
    release()
  }
})
