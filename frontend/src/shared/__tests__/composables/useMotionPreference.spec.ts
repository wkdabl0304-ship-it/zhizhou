/** 首页动效回归：验证系统减少动态效果、主动关闭与页面可见性监听的生命周期。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'
import { useMotionPreference } from '@/shared/composables/useMotionPreference'

const wrappers: VueWrapper[] = []
let media: EventTarget & { matches: boolean }

// 只模拟组合函数使用的媒体查询事件，避免读取运行测试机器的系统偏好。
beforeEach(() => {
  media = Object.assign(new EventTarget(), { matches: false })
  vi.stubGlobal('matchMedia', () => media)
})

// 卸载先触发监听清理，再恢复文档可见性和媒体查询替身。
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

/** 创建动效状态测试宿主，返回组件及状态供测试驱动和断言；监听清理使用真实 Vue 生命周期。 */
function renderMotion() {
  let motion: ReturnType<typeof useMotionPreference> | undefined
  const Host = defineComponent({
    // 挂载时创建监听，卸载时应由组合函数解除，测试无需模拟框架生命周期。
    setup() {
      motion = useMotionPreference()
      return {}
    },
    template: '<div />',
  })
  const wrapper = mount(Host)
  wrappers.push(wrapper)
  return { wrapper, motion: motion! }
}

describe('首页动效生命周期', () => {
  // 系统减少动态效果优先，恢复系统设置后仍尊重调用方主动关闭的请求。
  it('动效请求受系统减少动态效果约束，主动关闭后不会被系统恢复覆盖', async () => {
    const { motion } = renderMotion()
    expect(motion.enabled.value).toBe(true)
    media.matches = true
    media.dispatchEvent(Object.assign(new Event('change'), { matches: true }))
    await nextTick()
    expect(motion.enabled.value).toBe(false)
    expect(motion.requested.value).toBe(true)
    motion.requested.value = false
    media.matches = false
    media.dispatchEvent(Object.assign(new Event('change'), { matches: false }))
    await nextTick()
    expect(motion.enabled.value).toBe(false)
    motion.requested.value = true
    expect(motion.enabled.value).toBe(true)
  })

  // 后台只改变暂停状态，不重置动效请求；组件卸载后不再接收文档事件。
  it('页面隐藏后保留请求，卸载后停止响应可见性事件', async () => {
    const { wrapper, motion } = renderMotion()
    const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
    document.dispatchEvent(new Event('visibilitychange'))
    await nextTick()
    expect(motion.visible.value).toBe(false)
    expect(motion.requested.value).toBe(true)
    expect(motion.enabled.value).toBe(true)
    wrapper.unmount()
    visibility.mockReturnValue('visible')
    document.dispatchEvent(new Event('visibilitychange'))
    expect(motion.visible.value).toBe(false)
  })
})
