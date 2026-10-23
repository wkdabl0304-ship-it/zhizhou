/** 媒体查询生命周期：使用真实 Vue 挂载验证初始值、事件更新及卸载后的监听释放。 */
import { describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { useMediaQuery } from '../../composables/useMediaQuery'

describe('响应式媒体查询', () => {
  it('读取当前断点并只在挂载期间响应变化', async () => {
    const media = Object.assign(new EventTarget(), { matches: true })
    const remove = vi.spyOn(media, 'removeEventListener')
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => media),
    )
    const Host = defineComponent({
      // 宿主仅展示组合函数公开值，清理通过正常组件生命周期触发。
      setup: () => ({ narrow: useMediaQuery('(max-width: 760px)') }),
      template: '<span>{{ narrow }}</span>',
    })
    const wrapper = mount(Host)
    expect(wrapper.text()).toBe('true')
    media.dispatchEvent(Object.assign(new Event('change'), { matches: false }))
    await nextTick()
    expect(wrapper.text()).toBe('false')
    wrapper.unmount()
    expect(remove).toHaveBeenCalledWith('change', expect.any(Function))
  })
})
