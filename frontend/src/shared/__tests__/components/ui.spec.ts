/** 公共包装组件：验证自有按钮语义、属性透传与输入框观察器清理，不测试第三方内部实现。 */
import { describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import UiModal from '../../components/ui/UiModal.vue'
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

// Portal 内的编辑器必须独立响应关闭，不能带走仍打开的供应商主面板。
it('嵌套编辑弹窗关闭只影响当前层，保留主面板和可访问标题', async () => {
  const childOpen = ref(false)
  const parentClose = vi.fn<(open: boolean) => void>()
  const Host = defineComponent({
    // 通过真实按钮打开第二层，让公共模态组件负责其生命周期。
    setup: () => () =>
      h(
        UiModal,
        {
          open: true,
          title: '供应商面板',
          description: '选择连接与模型',
          'onUpdate:open': parentClose,
        },
        {
          default: () => [
            h(
              'button',
              {
                onClick: () => {
                  childOpen.value = true
                },
              },
              '编辑配置',
            ),
            childOpen.value
              ? h(
                  UiModal,
                  {
                    open: true,
                    editor: true,
                    title: '编辑配置',
                    description: '修改连接参数',
                    'onUpdate:open': () => {
                      childOpen.value = false
                    },
                  },
                  { default: () => h('input', { 'aria-label': '配置名称' }) },
                )
              : null,
          ],
        },
      ),
  })
  mount(Host, { attachTo: document.body })
  await flushPromises()
  const edit = [...document.querySelectorAll<HTMLButtonElement>('button')].find(
    (button) => button.textContent === '编辑配置',
  )!
  edit.click()
  await flushPromises()
  expect(document.querySelectorAll('[role="dialog"]')).toHaveLength(2)
  document.querySelector<HTMLButtonElement>('.config-modal--editor [aria-label="关闭"]')!.click()
  await flushPromises()
  expect(parentClose).not.toHaveBeenCalled()
  expect(document.querySelectorAll('[role="dialog"]')).toHaveLength(1)
  expect(document.querySelector('[role="dialog"]')?.textContent).toContain('供应商面板')
})

// 放弃草稿同时卸载确认层和编辑层，不能由最后卸载的确认框抢走主面板焦点。
it('同帧关闭编辑器和确认框后焦点回到主面板入口', async () => {
  const Host = defineComponent({
    components: { UiModal },
    setup: () => ({
      editing: ref(false),
      discarding: ref(false),
      trigger: ref<HTMLElement | null>(null),
    }),
    template:
      '<main><h1 tabindex="-1">页面标题</h1><UiModal :open="true" title="主面板" description="管理连接"><button ref="trigger" @click="editing = true">打开编辑</button><UiModal v-if="editing" :open="true" editor :return-focus="trigger" title="编辑连接" description="修改参数"><button @click="discarding = true">关闭编辑</button><UiModal v-if="discarding" :open="true" title="放弃草稿" description="不保存修改"><button @click="editing = false">确认放弃</button></UiModal></UiModal></UiModal></main>',
  })
  mount(Host, { attachTo: document.body })
  await flushPromises()
  const trigger = [...document.querySelectorAll<HTMLButtonElement>('button')].find(
    (button) => button.textContent === '打开编辑',
  )!
  trigger.focus()
  trigger.click()
  await flushPromises()
  const close = [...document.querySelectorAll<HTMLButtonElement>('button')].find(
    (button) => button.textContent === '关闭编辑',
  )!
  close.focus()
  close.click()
  await flushPromises()
  expect(document.querySelectorAll('[role="dialog"]')).toHaveLength(3)
  const discard = [...document.querySelectorAll<HTMLButtonElement>('button')].find(
    (button) => button.textContent === '确认放弃',
  )!
  discard.focus()
  discard.click()
  await flushPromises()
  await vi.waitFor(() => expect(document.activeElement).toBe(trigger))
  expect(document.querySelectorAll('[role="dialog"]')).toHaveLength(1)
})
