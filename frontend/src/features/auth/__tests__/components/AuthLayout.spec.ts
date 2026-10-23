/** 认证外壳动效回归：验证全页背景归属、系统偏好、后台暂停与卸载清理，不请求后端。 */
import { createTestPinia as createPinia } from '@tests/support/vitest/mount'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, RouterLinkStub, type VueWrapper } from '@vue/test-utils'
import { disposePinia, type Pinia } from 'pinia'
import { h, nextTick } from 'vue'
import AuthLayout from '@/features/auth/AuthLayout.vue'
import AuthForm from '@/features/auth/AuthForm.vue'
import type { AuthMode } from '@/features/auth/types'

let pinia: Pinia
let wrapper: VueWrapper | undefined
let media: EventTarget & { matches: boolean }

// 用真实 EventTarget 模拟系统偏好变化，固定前台状态，不依赖测试机器的系统配置。
beforeEach(() => {
  pinia = createPinia()
  media = Object.assign(new EventTarget(), { matches: false })
  vi.stubGlobal('matchMedia', () => media)
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
})

// 先卸载外壳释放监听，再还原文档和媒体查询替身。
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  disposePinia(pinia)
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

/** 挂载包含真实认证表单的外壳，同时验证构图调整后输入、校验与动效能协作。 */
function renderLayout(mode: AuthMode = 'login') {
  wrapper = mount(AuthLayout, {
    global: { plugins: [pinia], stubs: { RouterLink: RouterLinkStub } },
    // 用实际表单消费外壳插槽，覆盖登录与注册共享布局，而非仅挂载占位元素。
    slots: { default: () => h(AuthForm, { mode }) },
  })
  return wrapper
}

describe('认证背景与动效生命周期', () => {
  // 背景与主分栏并列归属整页，避免再次被左侧内容区域裁切；装饰不占据交互焦点。
  it('整页共用一个装饰背景，默认启用已有山水动效', () => {
    const page = renderLayout()
    expect(page.findAll('.river-backdrop')).toHaveLength(1)
    expect(page.get('.river-backdrop').element.parentElement).toBe(page.element)
    expect(page.get('.river-backdrop').attributes('aria-hidden')).toBe('true')
    expect(page.get('.river-backdrop').attributes('data-motion')).toBe('on')
    expect(page.get('.auth-page').attributes('data-visible')).toBe('true')
  })

  // 收拢内容和移除面板只改变构图，两种表单仍能先展示字段错误，再提交有效凭据。
  it.each(['login', 'register'] as const)('%s 布局内保留字段校验与有效提交', async (mode) => {
    const page = renderLayout(mode)
    await page.get('form').trigger('submit')
    expect(page.text()).toContain('请输入用户名')
    expect(page.getComponent(AuthForm).emitted('submit')).toBeUndefined()
    await page.get('[name="username"]').setValue('Lin_Zhou')
    await page.get('[name="password"]').setValue(' password ')
    if (mode === 'register') await page.get('[name="confirmation"]').setValue(' password ')
    await page.get('form').trigger('submit')
    expect(page.getComponent(AuthForm).emitted('submit')).toEqual([
      [{ username: 'lin_zhou', password: ' password ' }],
    ])
    expect(page.get('[name="username"]').attributes('aria-invalid')).toBe('false')
  })

  // 系统请求减少动态效果时，根容器与背景必须同步静止，恢复时不丢失正在填写的数据。
  it('系统偏好实时控制动效，切换不重建表单输入', async () => {
    const page = renderLayout()
    await page.get('input').setValue('尚未提交的用户名')
    media.matches = true
    media.dispatchEvent(Object.assign(new Event('change'), { matches: true }))
    await nextTick()
    expect(page.get('.auth-page').attributes('data-motion')).toBe('off')
    expect(page.get('.river-backdrop').attributes('data-motion')).toBe('off')
    expect((page.get('input').element as HTMLInputElement).value).toBe('尚未提交的用户名')
    media.matches = false
    media.dispatchEvent(Object.assign(new Event('change'), { matches: false }))
    await nextTick()
    expect(page.get('.river-backdrop').attributes('data-motion')).toBe('on')
    expect((page.get('input').element as HTMLInputElement).value).toBe('尚未提交的用户名')
  })

  // 首次打开时就遵守系统偏好，不能先播放入场动画再等待用户设置变更。
  it('初次挂载即尊重减少动态效果设置', () => {
    media.matches = true
    const page = renderLayout()
    expect(page.get('.auth-page').attributes('data-motion')).toBe('off')
    expect(page.get('.river-backdrop').attributes('data-motion')).toBe('off')
  })

  // 切后台只暂停进度而不关闭动效；卸载同时释放文档和媒体监听，避免反复进出页面累积。
  it('后台暂停、回到前台继续，并在卸载后解除监听', async () => {
    const removeDocument = vi.spyOn(document, 'removeEventListener')
    const removeMedia = vi.spyOn(media, 'removeEventListener')
    const page = renderLayout()
    const visibility = vi.spyOn(document, 'visibilityState', 'get')
    visibility.mockReturnValue('hidden')
    document.dispatchEvent(new Event('visibilitychange'))
    await nextTick()
    expect(page.get('.auth-page').attributes('data-visible')).toBe('false')
    expect(page.get('.river-backdrop').attributes('data-motion')).toBe('on')
    visibility.mockReturnValue('visible')
    document.dispatchEvent(new Event('visibilitychange'))
    await nextTick()
    expect(page.get('.auth-page').attributes('data-visible')).toBe('true')
    page.unmount()
    wrapper = undefined
    expect(removeDocument).toHaveBeenCalledWith('visibilitychange', expect.any(Function))
    expect(removeMedia).toHaveBeenCalledWith('change', expect.any(Function))
  })
})
