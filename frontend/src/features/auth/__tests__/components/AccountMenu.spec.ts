/** 账号菜单组件回归：验证紧凑入口、按需展开明暗选择、开发导航、退出清理及键盘焦点，不请求真实后端。 */
import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createTestPinia } from '@tests/support/vitest/mount'
import { authenticate } from '@tests/support/vitest/auth'
import { useAuthStore } from '@/features/auth/store'
import { useThemeStore, THEME_STORAGE_KEY } from '@/shared/stores/theme'
import AccountMenu from '../../components/AccountMenu.vue'

const fetchMock = vi.fn<typeof fetch>()
beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  localStorage.clear()
})

/** 通过实际账号和路由挂载菜单，使用 Portal 节点执行真实用户操作。 */
async function open(compact = false) {
  const pinia = createTestPinia()
  await authenticate(pinia, fetchMock)
  const auth = useAuthStore(pinia)
  const theme = useThemeStore(pinia)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<p>工作区</p>' } },
      { path: '/dev/ui', component: { template: '<p>组件预览</p>' } },
    ],
  })
  await router.push('/')
  const host = mount(AccountMenu, {
    props: { compact },
    attachTo: document.body,
    global: { plugins: [pinia, router] },
  })
  const body = new DOMWrapper(document.body)
  const trigger = host.get<HTMLButtonElement>('[aria-label="账号菜单"]')
  trigger.element.focus()
  expect(body.find('[role="menu"]').exists()).toBe(false)
  await trigger.trigger('click')
  await flushPromises()
  return { host, body, trigger, theme, auth, router }
}

it.each([false, true])('收起状态 %s 下头像菜单默认只展示紧凑操作行', async (compact) => {
  const { host, body, trigger, auth } = await open(compact)
  expect(host.get('.profile-name').text()).toBe(auth.user!.username)
  expect(trigger.attributes('aria-expanded')).toBe('true')
  expect(body.findAll('[role="menu"]')).toHaveLength(1)
  expect(body.find('.appearance-heading').exists()).toBe(false)
  expect(body.findAll('[role="menuitemradio"]')).toHaveLength(0)
  expect(body.get('[aria-label="外观"]').attributes('aria-expanded')).toBe('false')
  expect(
    body.findAll('[role="menuitem"]').map((item) => item.attributes('aria-label') ?? item.text()),
  ).toEqual(['外观', '组件预览', '退出登录'])
  expect(host.find('[aria-label="退出登录"]').exists()).toBe(false)
})

it('切换主题立即生效并持久化，关闭后恢复头像焦点', async () => {
  const { body, trigger, theme } = await open()
  await body.get('[role="menuitem"][aria-label="外观"]').trigger('click')
  await flushPromises()
  expect(body.get('[role="menu"]').isVisible()).toBe(true)
  await body.get('[role="menuitemradio"][aria-label="深色"]').trigger('click')
  await flushPromises()
  expect(theme.theme).toBe('dark')
  expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
  expect(body.find('[role="menu"]').exists()).toBe(false)
  await vi.waitFor(() => expect(document.activeElement).toBe(trigger.element))
})

it('Esc 取消菜单保持身份并恢复头像焦点', async () => {
  const { body, trigger, auth } = await open()
  body
    .get('[role="menuitem"]')
    .element.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }),
    )
  await flushPromises()
  expect(auth.isAuthenticated).toBe(true)
  expect(body.find('[role="menu"]').exists()).toBe(false)
  await vi.waitFor(() => expect(document.activeElement).toBe(trigger.element))
})

it('开发预览作为同层菜单项导航，路由变化收起浮层', async () => {
  const { body, router } = await open()
  await body.get('a[href="/dev/ui"]').trigger('click')
  await flushPromises()
  expect(router.currentRoute.value.path).toBe('/dev/ui')
  expect(body.find('[role="menu"]').exists()).toBe(false)
})

it('退出登录清理当前身份且不伪造服务端退出请求', async () => {
  const { body, auth } = await open()
  await body.get('.account-menu-item:last-child').trigger('click')
  await flushPromises()
  expect(auth.isAuthenticated).toBe(false)
  expect(auth.accessToken).toBe('')
  expect(body.find('[role="menu"]').exists()).toBe(false)
  expect(fetchMock).not.toHaveBeenCalled()
})

it('切换侧栏形态会关闭旧浮层，头像入口保持可操作', async () => {
  const { host, body, trigger } = await open()
  await host.setProps({ compact: true })
  await flushPromises()
  expect(body.find('[role="menu"]').exists()).toBe(false)
  await trigger.trigger('click')
  await flushPromises()
  expect(body.get('[role="menu"]').isVisible()).toBe(true)
})

// 悬停只反馈可操作状态，显式点击才展开；关闭重开恢复紧凑形态。
it('外观仅在点击后展开，可再次收起，关闭菜单后重置展开状态', async () => {
  const { body, trigger, theme } = await open()
  const appearance = body.get('[role="menuitem"][aria-label="外观"]')
  await appearance.trigger('pointermove', { pointerType: 'mouse' })
  expect(body.find('[role="menuitemradio"]').exists()).toBe(false)
  await appearance.trigger('click')
  await flushPromises()
  expect(appearance.attributes('aria-expanded')).toBe('true')
  expect(body.findAll('[role="menuitemradio"]')).toHaveLength(2)
  expect(theme.theme).toBe('light')
  await appearance.trigger('click')
  await flushPromises()
  expect(body.find('[role="menuitemradio"]').exists()).toBe(false)
  await appearance.trigger('click')
  await flushPromises()
  body
    .get('[role="menuitemradio"]')
    .element.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }),
    )
  await flushPromises()
  await trigger.trigger('click')
  await flushPromises()
  expect(body.find('[role="menuitemradio"]').exists()).toBe(false)
  expect(body.get('[aria-label="外观"]').attributes('aria-expanded')).toBe('false')
})
