/** 应用路由集成：验证未知入口与主动身份失效后的导航，不依赖真实服务。 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'
import App from '@/App.vue'
import { createAppRouter } from '@/router'
import { useAuthStore } from '@/features/auth/store'
import { createTestPinia } from '@tests/support/vitest/mount'
import { installMediaQuery } from '@tests/support/vitest/browser'
import { authenticate } from '@tests/support/vitest/auth'
import { response } from '@tests/support/vitest/http'

const fetchMock = vi.fn<typeof fetch>()
// 只安装本组涉及的断点和 HTTP 接口，组件、路由和状态保持真实协作。
beforeEach(() => {
  installMediaQuery()
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

describe('应用入口与身份边界', () => {
  it('未知路径展示站内兜底页面，不触发身份或聊天请求', async () => {
    const pinia = createTestPinia()
    const router = createAppRouter(createMemoryHistory())
    await router.push('/missing-page')
    await router.isReady()
    const wrapper = mount(App, { global: { plugins: [pinia, router] } })
    expect(wrapper.text()).toContain('这条航线还没有开通')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('已挂载工作区身份失效后回到登录，保留返回地址并卸载消息输入', async () => {
    const pinia = createTestPinia()
    await authenticate(pinia, fetchMock)
    fetchMock.mockResolvedValue(response({ items: [], next_cursor: null }))
    const router = createAppRouter(createMemoryHistory())
    await router.push('/?from=test')
    await router.isReady()
    const wrapper = mount(App, { global: { plugins: [pinia, router] } })
    await flushPromises()
    expect(wrapper.find('textarea').exists()).toBe(true)
    useAuthStore(pinia).invalidate('test-access-token')
    // 懒加载认证页完成后才确认导航，避免把一次微任务刷新当作路由完成。
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('login'))
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/?from=test')
    expect(wrapper.find('textarea').exists()).toBe(false)
  })
})
