/** 开发控件页浏览器验收：键盘选择、错误与禁用、标签点击、明暗主题和窄屏不溢出。 */
import { expect, test } from '@playwright/test'

test('共享控件支持完整表单操作、键盘取消与明暗主题', async ({ page }, testInfo) => {
  const errors: string[] = []
  // 开发预览的任何未捕获浏览器异常都使验收失败。
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/dev/ui')
  const controls = page.getByRole('region', { name: '基础表单控件', exact: true })
  await expect(controls).toBeVisible()
  const feedback = page.getByRole('region', { name: '标签与失败反馈', exact: true })
  await expect(feedback.locator('.ui-tag').filter({ hasText: '本人' })).toBeVisible()
  const sizes = page.getByRole('group', { name: '标签尺寸对比', exact: true })
  // 使用真实排版验证尺寸由留白拉开；同组字号一致，窄屏时对照区不得撑宽页面。
  const metrics = await sizes.locator('.ui-tag').evaluateAll((tags) =>
    tags.map((tag) => {
      const style = getComputedStyle(tag)
      return {
        height: tag.getBoundingClientRect().height,
        paddingInline: Number.parseFloat(style.paddingLeft),
        paddingBlock: Number.parseFloat(style.paddingTop),
        fontSize: style.fontSize,
      }
    }),
  )
  expect(metrics).toHaveLength(4)
  for (let index = 1; index < metrics.length; index++) {
    expect(metrics[index]!.height).toBeGreaterThan(metrics[index - 1]!.height)
    expect(metrics[index]!.paddingInline).toBeGreaterThan(metrics[index - 1]!.paddingInline)
    expect(metrics[index]!.paddingBlock).toBeGreaterThan(metrics[index - 1]!.paddingBlock)
  }
  expect(metrics[0]!.fontSize).toBe(metrics[1]!.fontSize)
  expect(metrics[2]!.fontSize).toBe(metrics[3]!.fontSize)
  expect(metrics[0]!.height).toBeLessThan(20)
  await sizes.screenshot({ path: testInfo.outputPath('tag-sizes-light.png') })
  const secondary = page.getByRole('button', { name: '次要操作', exact: true })
  // 错误容器的语义色不应改变普通重试按钮，两个入口使用同一公共按钮层级。
  const actionColor = await secondary.evaluate((element) => getComputedStyle(element).color)
  await expect(feedback.getByRole('button', { name: '重试示例' })).toHaveCSS('color', actionColor)
  const lightweight = page.getByRole('button', { name: '轻量操作', exact: true })
  await expect(lightweight).toHaveCSS('border-top-style', 'solid')
  await expect(lightweight).toHaveCSS('border-top-width', '1px')
  await lightweight.focus()
  await expect(lightweight).toBeFocused()
  await page.screenshot({ path: testInfo.outputPath('foundation-light.png'), fullPage: true })
  await page.screenshot({ path: testInfo.outputPath('foundation-light-viewport.png') })
  await feedback.screenshot({ path: testInfo.outputPath('feedback-light.png') })
  await feedback.getByRole('button', { name: '重试示例', exact: true }).click()
  await expect(feedback.getByText('暂时无法读取目录', { exact: true })).toHaveCount(0)
  await expect(feedback.getByRole('button', { name: '再次模拟失败' })).toBeVisible()
  await expect(feedback).not.toContainText('成功')
  const input = page.getByRole('textbox', { name: '示例用户名', exact: true })
  await input.fill('lin_zhou')
  expect(await input.evaluate((element) => getComputedStyle(element).outlineStyle)).toBe('none')
  const trigger = page.getByRole('combobox', { name: '示例账号状态', exact: true })
  await trigger.focus()
  await page.keyboard.press('ArrowDown')
  await expect(page.getByRole('option', { name: '全部状态', exact: true })).toBeFocused()
  await page.keyboard.press('End')
  await expect(page.getByRole('option', { name: '已停用', exact: true })).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(trigger).toContainText('已停用')
  await trigger.press('ArrowDown')
  await expect(page.getByRole('option', { name: '已停用', exact: true })).toBeFocused()
  await page.keyboard.press('Home')
  await expect(page.getByRole('option', { name: '全部状态', exact: true })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(trigger).toContainText('已停用')
  await expect(trigger).toBeFocused()
  await page.getByText('仅无部门', { exact: true }).click()
  const checkbox = page.getByRole('checkbox', { name: '仅无部门', exact: true })
  await expect(checkbox).toBeChecked()
  await checkbox.hover()
  await expect(checkbox).toHaveCSS('cursor', 'pointer')
  await page.getByRole('button', { name: '查看表单结果', exact: true }).click()
  await expect(
    page.getByRole('status').filter({ hasText: 'lin_zhou · 已停用 · 仅无部门' }),
  ).toBeVisible()
  await expect(
    page.getByRole('checkbox', { name: '已选中 · 不可修改', exact: true }),
  ).toBeDisabled()
  await controls.screenshot({ path: testInfo.outputPath('controls-light.png') })
  await page.getByRole('button', { name: '外观 浅色', exact: true }).click()
  await page.getByRole('menuitemradio', { name: '深色', exact: true }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await sizes.screenshot({ path: testInfo.outputPath('tag-sizes-dark.png') })
  await feedback.getByRole('button', { name: '再次模拟失败' }).click()
  const darkActionColor = await secondary.evaluate((element) => getComputedStyle(element).color)
  await expect(feedback.getByRole('button', { name: '重试示例' })).toHaveCSS(
    'color',
    darkActionColor,
  )
  await expect(lightweight).toHaveCSS('border-top-style', 'solid')
  await feedback.screenshot({ path: testInfo.outputPath('feedback-dark.png') })
  await page.getByRole('heading', { name: '组件与交互预览', exact: true }).scrollIntoViewIfNeeded()
  await page.screenshot({ path: testInfo.outputPath('foundation-dark-viewport.png') })
  await page.screenshot({ path: testInfo.outputPath('foundation-dark.png'), fullPage: true })
  await controls.screenshot({ path: testInfo.outputPath('controls-dark.png') })
  await trigger.click()
  await expect(page.getByRole('option', { name: '已停用', exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('controls-menu-dark.png') })
  expect(
    await page.locator('body').evaluate((element) => element.scrollWidth <= window.innerWidth),
  ).toBe(true)
  expect(errors).toEqual([])
})
