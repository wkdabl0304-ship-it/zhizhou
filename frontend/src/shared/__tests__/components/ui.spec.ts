/** 公共包装组件：验证自有按钮语义、属性透传与输入框观察器清理，不测试第三方内部实现。 */
import { describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import UiButton from '../../components/ui/UiButton.vue'
import UiIconButton from '../../components/ui/UiIconButton.vue'
import UiAutoTextarea from '../../components/ui/UiAutoTextarea.vue'

describe('基础按钮', () => {
  it('透传原生事件和类型，加载状态禁止重复点击并暴露忙碌语义', async () => {
    const click = vi.fn<(event: MouseEvent) => void>()
    const wrapper = mount(UiButton, {
      props: { type: 'submit', onClick: click },
      slots: { default: '保存' },
    })
    expect(wrapper.attributes('type')).toBe('submit')
    await wrapper.trigger('click')
    expect(click).toHaveBeenCalledOnce()
    await wrapper.setProps({ loading: true })
    expect(wrapper.attributes('aria-busy')).toBe('true')
    expect(wrapper.attributes('disabled')).toBeDefined()
    await wrapper.trigger('click')
    expect(click).toHaveBeenCalledOnce()
  })

  it('图标按钮保留可访问名称与禁用属性', () => {
    const wrapper = mount(UiIconButton, { props: { label: '删除会话', disabled: true } })
    expect(wrapper.attributes('aria-label')).toBe('删除会话')
    expect(wrapper.attributes('disabled')).toBeDefined()
    expect(wrapper.attributes('type')).toBe('button')
  })
})

describe('自适应输入框', () => {
  it('输入与宽度变化后重测高度，卸载后释放观察器', async () => {
    let notify!: ResizeObserverCallback
    const observe = vi.fn<(target: Element) => void>()
    const disconnect = vi.fn<() => void>()
    // 观察器替身只提供通知入口，不模拟浏览器布局算法。
    class Observer {
      constructor(callback: ResizeObserverCallback) {
        notify = callback
      }
      observe = observe
      disconnect = disconnect
      unobserve = vi.fn<(target: Element) => void>()
    }
    vi.stubGlobal('ResizeObserver', Observer)
    const wrapper = mount(UiAutoTextarea, {
      props: { label: '消息', modelValue: '' },
      attachTo: document.body,
    })
    const element = wrapper.get('textarea').element
    const height = vi.spyOn(element, 'scrollHeight', 'get').mockReturnValue(80)
    await wrapper.setProps({ modelValue: '多行内容' })
    await flushPromises()
    expect(element.style.height).toBe('80px')
    expect(observe).toHaveBeenCalledWith(element)
    height.mockReturnValue(120)
    notify([{ contentRect: { width: 300 } } as ResizeObserverEntry], {} as ResizeObserver)
    await flushPromises()
    expect(element.style.height).toBe('120px')
    wrapper.vm.focus()
    expect(document.activeElement).toBe(element)
    wrapper.unmount()
    expect(disconnect).toHaveBeenCalledOnce()
  })
})
