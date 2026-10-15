/** 消息安全与复制回归：验证文本块不会被当作 HTML，并隔离浏览器剪贴板替身。 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { TooltipProvider } from 'reka-ui'
import MessageItem from '@/components/chat/MessageItem.vue'
import type { ChatMessage } from '@/types/chat'

const wrappers: VueWrapper[] = []
/** 提供提示上下文并渲染真实消息组件，不替换文本块渲染过程。 */
function renderMessage(message: ChatMessage) {
  const Host = defineComponent({
    components: { MessageItem, TooltipProvider },
    // 将测试数据交给模板，检查实际 DOM 而不是组件内部计算结果。
    setup: () => ({ message }),
    template: '<TooltipProvider><MessageItem :message="message" /></TooltipProvider>',
  })
  const wrapper = mount(Host)
  wrappers.push(wrapper)
  return wrapper
}

// 卸载实例并撤销剪贴板全局替身，不访问系统剪贴板。
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  vi.unstubAllGlobals()
})

describe('消息展示', () => {
  // 用户与模型文本一律插值渲染，代码中的标签也不创建元素。
  it('段落、列表和代码安全呈现为文本', () => {
    const wrapper = renderMessage({
      id: 'safe',
      role: 'assistant',
      blocks: [
        { type: 'paragraph', text: '<img src=x onerror=alert(1)>' },
        { type: 'list', items: ['<b>列表内容</b>'] },
        { type: 'code', language: 'html', text: '<iframe src="https://example.com"></iframe>' },
      ],
    })
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.find('iframe').exists()).toBe(false)
    expect(wrapper.find('b').exists()).toBe(false)
    expect(wrapper.get('code').text()).toContain('<iframe')
  })

  // 模拟剪贴板拒绝权限，必须给出可见降级提示而非未处理异常。
  it('复制失败后提供手动复制提示', async () => {
    const writeText = vi
      .fn<(text: string) => Promise<void>>()
      .mockRejectedValue(new Error('denied'))
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    const wrapper = renderMessage({
      id: 'copy',
      role: 'assistant',
      blocks: [{ type: 'list', items: ['第一项', '第二项'] }],
    })
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith('- 第一项\n- 第二项')
    expect(wrapper.get('[role="status"]').text()).toContain('复制失败')
  })
})
