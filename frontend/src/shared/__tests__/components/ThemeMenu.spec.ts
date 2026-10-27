/** 外观预览菜单回归：使用真实 Reka 单选、焦点与 Portal，验证鼠标、键盘和持久化。 */
import { beforeEach, expect, it, vi } from 'vitest'
import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import { createTestPinia } from '@tests/support/vitest/mount'
import { useThemeStore, THEME_STORAGE_KEY } from '../../stores/theme'
import ThemeMenu from '../../components/ThemeMenu.vue'

beforeEach(() => localStorage.clear())

/** 挂载正常或收起的外观入口，并展开真实菜单供交互验证。 */
async function open(compact = false, dark = false) {
  const pinia = createTestPinia()
  const theme = useThemeStore(pinia)
  if (dark) theme.setTheme('dark')
  const host = mount(ThemeMenu, {
    attachTo: document.body,
    props: { compact },
    global: { plugins: [pinia] },
  })
  const trigger = host.get<HTMLButtonElement>('button')
  trigger.element.focus()
  await trigger.trigger('click')
  await flushPromises()
  return { host, page: new DOMWrapper(document.body), theme, trigger }
}

it('显示两张独立配色预览，选择后应用并保存主题且关闭菜单', async () => {
  const { page, theme, trigger } = await open()
  expect(page.findAll('[role="menuitemradio"]')).toHaveLength(2)
  expect(page.text()).toContain('青碧 · 朱砂')
  expect(page.text()).toContain('靛夜 · 月金')
  expect(page.get('[aria-label="浅色"]').attributes('aria-checked')).toBe('true')
  await page.get('[aria-label="深色"]').trigger('click')
  await flushPromises()
  expect(theme.theme).toBe('dark')
  expect(document.documentElement.dataset.theme).toBe('dark')
  expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
  expect(trigger.text()).toContain('深色')
  expect(page.find('[role="menu"]').exists()).toBe(false)
})

it('左右键只移动焦点，Enter 才确认，允许用键盘浏览双列预览', async () => {
  const { page, theme } = await open()
  const light = page.get<HTMLElement>('[aria-label="浅色"]')
  const dark = page.get<HTMLElement>('[aria-label="深色"]')
  light.element.focus()
  await light.trigger('keydown', { key: 'ArrowRight' })
  expect(document.activeElement).toBe(dark.element)
  expect(theme.theme).toBe('light')
  await dark.trigger('keydown', { key: 'Enter' })
  await flushPromises()
  expect(theme.theme).toBe('dark')
})

it('浏览另一方案后 Esc 关闭菜单，保持已保存偏好并恢复入口焦点', async () => {
  const { page, theme, trigger } = await open(false, true)
  const dark = page.get<HTMLElement>('[aria-label="深色"]')
  const light = page.get<HTMLElement>('[aria-label="浅色"]')
  dark.element.focus()
  await dark.trigger('keydown', { key: 'ArrowLeft' })
  expect(document.activeElement).toBe(light.element)
  // 从候选项派发真实可取消键盘事件，覆盖菜单关闭与焦点恢复，不能仅卸载菜单模拟取消。
  light.element.dispatchEvent(
    new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }),
  )
  await flushPromises()
  expect(page.find('[role="menu"]').exists()).toBe(false)
  expect(theme.theme).toBe('dark')
  expect(document.documentElement.dataset.theme).toBe('dark')
  expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
  await vi.waitFor(() => expect(document.activeElement).toBe(trigger.element))
})

it('收起入口保留可访问名称，并同步已恢复的深色单选状态', async () => {
  const { page, trigger } = await open(true, true)
  expect(trigger.attributes('aria-label')).toBe('选择外观')
  expect(page.get('[aria-label="深色"]').attributes('aria-checked')).toBe('true')
  expect(page.get('[aria-label="浅色"]').attributes('aria-checked')).toBe('false')
})
