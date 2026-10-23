/** 消息富文本与复制回归：区分助手 Markdown 和用户纯文本，并隔离浏览器剪贴板替身。 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { defineComponent, nextTick, shallowRef } from 'vue'
import MessageList from '@/features/chat/components/MessageList.vue'
import { TooltipProvider } from 'reka-ui'
import MessageItem from '@/features/chat/components/MessageItem.vue'
import type { ChatMessage } from '@/features/chat/types'

const wrappers: VueWrapper[] = []
/** 挂载指定消息以测试真实展示与复制行为；提供 Tooltip 上下文，不替换正文渲染逻辑。 */
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
  // 以 DOM 中实际消息数量模拟高度，验证前插历史维持原位置，而非跳到末尾。
  it('前插更早消息时按高度差保持阅读位置', async () => {
    // 测试只替换整页消息，浅层引用避免递归工具 JSON 参与 Vue 深层类型展开。
    const messages = shallowRef<ChatMessage[]>([
      { id: 'recent', role: 'user', blocks: [{ type: 'paragraph', text: '最近消息' }] },
    ])
    const Host = defineComponent({
      components: { TooltipProvider, MessageList },
      // 保持真实列表生命周期，使父滚动容器在 DOM 更新前后产生可测量的高度差。
      setup: () => ({ messages }),
      template:
        '<TooltipProvider><section><MessageList :messages="messages" conversation-id="server-session" /></section></TooltipProvider>',
    })
    const wrapper = mount(Host)
    wrappers.push(wrapper)
    await nextTick()
    const scroller = wrapper.get('section').element
    // jsdom 没有排版引擎；用已渲染节点数量提供高度，避免测试绑定 Vue 更新实现。
    Object.defineProperty(scroller, 'scrollHeight', {
      configurable: true,
      get: () => scroller.querySelectorAll('article').length * 200,
    })
    scroller.scrollTop = 80
    messages.value = [
      { id: 'older', role: 'user', blocks: [{ type: 'paragraph', text: '较早消息' }] },
      ...messages.value,
    ]
    await flushPromises()
    expect(scroller.scrollTop).toBe(280)
    expect(wrapper.findAll('article').map((article) => article.text())).toEqual(
      expect.arrayContaining([
        expect.stringContaining('较早消息'),
        expect.stringContaining('最近消息'),
      ]),
    )
  })

  // 模型的原始 HTML 不作为网页执行，结构化预览代码中的标签也不创建元素。
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

  // 同一段 Markdown 在助手回复中排版，用户消息保持原始输入；整条回复复制保留 Markdown。
  it('助手支持 Markdown，用户保留纯文本，整条回复复制保留源文', async () => {
    const text = '**重要结论**\n\n- 第一步\n- 第二步'
    const assistant = renderMessage({
      id: 'rich',
      role: 'assistant',
      blocks: [{ type: 'paragraph', text }],
    })
    const user = renderMessage({ id: 'user', role: 'user', blocks: [{ type: 'paragraph', text }] })
    expect(assistant.get('strong').text()).toBe('重要结论')
    expect(assistant.findAll('ul li')).toHaveLength(2)
    expect(user.find('strong').exists()).toBe(false)
    expect(user.text()).toContain('**重要结论**')
    const writeText = vi.fn<(text: string) => Promise<void>>().mockResolvedValue()
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    await assistant.get('[aria-label="复制回复"]').trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith(text)
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
