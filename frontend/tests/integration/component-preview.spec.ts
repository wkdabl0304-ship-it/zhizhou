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
  await page.get('input[aria-label="示例用户名"]').setValue('lin_zhou')
  await chooseSelect(page.get('[role="combobox"][aria-label="示例账号状态"]'), 'inactive')
  const checkbox = new DOMWrapper(document.body)
    .findAll('.ui-checkbox')
    .find((row) => row.text() === '仅无部门')!
  await checkbox.trigger('click')
  await page.get('form[aria-label="控件联动示例"]').trigger('submit')
  expect(page.text()).toContain('lin_zhou · 已停用 · 仅无部门')
})
