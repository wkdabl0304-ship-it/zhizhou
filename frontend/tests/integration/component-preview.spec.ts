/** 开发预览集成：在真实路由和状态下验证共享输入、下拉与复选的表单联动。 */
import { beforeEach, expect, it } from 'vitest'
import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'
import App from '@/App.vue'
import { createAppRouter } from '@/router'
import { createTestPinia } from '@tests/support/vitest/mount'
import { installMediaQuery } from '@tests/support/vitest/browser'
import { chooseSelect } from '@tests/support/vitest/controls'

beforeEach(() => {
  installMediaQuery()
})

it('组件预览提供状态示例，并展示真实输入、选择和标签勾选的组合结果', async () => {
  const pinia = createTestPinia(),
    router = createAppRouter(createMemoryHistory())
  await router.push('/dev/ui')
  await router.isReady()
  const page = mount(App, { attachTo: document.body, global: { plugins: [pinia, router] } })
  await flushPromises()
  expect(page.text()).toContain('基础表单控件')
  expect(page.find('[aria-invalid="true"]').exists()).toBe(true)
  const feedback = page.get('section[aria-label="标签与失败反馈"]')
  expect(feedback.findAll('.ui-tag').map((tag) => tag.text())).toContain('本人')
  const sizes = feedback.get('[aria-label="标签尺寸对比"]')
  expect(sizes.findAll('.ui-tag').map((tag) => tag.text())).toEqual(Array(4).fill('已启用'))
  for (const size of ['xs', 'sm', 'md', 'lg'])
    expect(sizes.find(`.ui-tag--${size}`).exists()).toBe(true)
  await feedback.get('button').trigger('click')
  expect(feedback.text()).not.toContain('暂时无法读取目录')
  expect(feedback.text()).not.toContain('成功')
  expect(feedback.text()).toContain('再次模拟失败')
  await page.get('input[aria-label="示例用户名"]').setValue('lin_zhou')
  await chooseSelect(page.get('[role="combobox"][aria-label="示例账号状态"]'), 'inactive')
  const checkbox = new DOMWrapper(document.body)
    .findAll('.ui-checkbox')
    .find((row) => row.text() === '仅无部门')!
  await checkbox.trigger('click')
  await page.get('form[aria-label="控件联动示例"]').trigger('submit')
  expect(page.text()).toContain('lin_zhou · 已停用 · 仅无部门')
})
