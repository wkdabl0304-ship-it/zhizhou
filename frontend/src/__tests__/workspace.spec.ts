/** 工作空间集成回归：验证示例填入、发送后的焦点和会话切换；不连接网络或数据库。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent } from 'vue'
import { TooltipProvider } from 'reka-ui'
import ChatView from '@/views/ChatView.vue'
import WelcomeHeading from '@/components/chat/WelcomeHeading.vue'
import { controlledStream, eventFrame, success } from './helpers/chatStream'

const wrappers: VueWrapper[] = []
const fetchMock = vi.fn<typeof fetch>()
// jsdom 没有真实视口断点；桌面替身只提供组件实际使用的媒体查询监听接口。
beforeEach(() => {
  fetchMock.mockReset()
  // 回显实际 thread_id，验证页面经过真实 API 适配层更新消息，替身不连接模型。
  fetchMock.mockImplementation(async (_url, init) => {
    const { thread_id } = JSON.parse(init!.body as string) as { thread_id: string }
    return success(thread_id, '来自后端的回复')
  })
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('matchMedia', () => ({
    matches: false,
    addEventListener: vi.fn<() => void>(),
    removeEventListener: vi.fn<() => void>(),
  }))
})
// 卸载组件后再恢复全局替身，确保监听清理调用仍能访问原替身。
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

/** 用真实 Pinia 与 TooltipProvider 组合页面，只替换无关的路由链接。 */
function renderWorkspace() {
  const Host = defineComponent({
    components: { TooltipProvider, ChatView },
    template: '<TooltipProvider><ChatView /></TooltipProvider>',
  })
  const wrapper = mount(Host, {
    attachTo: document.body,
    global: { plugins: [createPinia()], stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
  wrappers.push(wrapper)
  return wrapper
}

describe('聊天工作空间', () => {
  // 首页输入实例会在发送时被替换，必须将焦点送到新对话页的输入框。
  it('建议只填入草稿，发送后创建对话并保持输入焦点', async () => {
    const wrapper = renderWorkspace()
    // 首页使用独立的现代宋体组件，正文与输入区继续使用公共无衬线字体。
    expect(wrapper.findComponent(WelcomeHeading).exists()).toBe(true)
    // 装饰跟随首页生命周期，进入正文后应释放背景，保持阅读区稳定。
    expect(wrapper.find('.river-backdrop').exists()).toBe(true)
    await wrapper.get('.suggestion').trigger('click')
    expect(wrapper.findAll('article')).toHaveLength(0)
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toContain('入职清单')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.findAll('article')).toHaveLength(2)
    expect(wrapper.find('.river-backdrop').exists()).toBe(false)
    expect(document.activeElement).toBe(wrapper.get('textarea').element)
    expect(wrapper.text()).toContain('来自后端的回复')
    expect(wrapper.text()).not.toContain('演示回复')
  })

  // 草稿不跨会话携带，防止切换后误发；会话正文仍由各自数据恢复。
  it('切换会话与新建时清除草稿', async () => {
    const wrapper = renderWorkspace()
    await wrapper.get('textarea').setValue('第一段对话')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    await wrapper.get('.new-chat-button').trigger('click')
    await wrapper.get('textarea').setValue('未发送的内容')
    await wrapper.get('.conversation-item').trigger('click')
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('')
    expect(wrapper.findAll('article')).toHaveLength(2)
    await wrapper.get('.new-chat-button').trigger('click')
    expect(wrapper.findAll('article')).toHaveLength(0)
    expect(wrapper.find('.welcome').exists()).toBe(true)
  })

  // 慢响应时输入区仍可编辑草稿，但再次 Enter 不应清空草稿或产生并发请求。
  it('等待期间阻止重复提交，失败后可继续发送', async () => {
    let rejectReply!: (reason: Error) => void
    fetchMock.mockImplementationOnce(
      () =>
        new Promise((_resolve, reject) => {
          rejectReply = reject
        }),
    )
    const wrapper = renderWorkspace()
    await wrapper.get('textarea').setValue('测试慢请求')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.get('[role="status"]').text()).toContain('正在整理思路')
    expect(document.activeElement).toBe(wrapper.get('textarea').element)
    await wrapper.get('textarea').setValue('下一条草稿')
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    await wrapper.get('textarea').trigger('keydown', { key: 'Enter' })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('下一条草稿')
    rejectReply(new TypeError('Failed to fetch'))
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('暂时无法获取回复')
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('来自后端的回复')
  })

  // 在流未完成时检查实际 DOM，确保增量可见、复制暂不可用，中断后仍保留部分正文。
  it('逐段展示回复，中断后保留文本和草稿并标明未完成', async () => {
    const stream = controlledStream()
    fetchMock.mockResolvedValueOnce(stream.response)
    const wrapper = renderWorkspace()
    await wrapper.get('textarea').setValue('流式回复测试')
    await wrapper.get('form').trigger('submit')
    const { thread_id } = JSON.parse(fetchMock.mock.calls[0]![1]!.body as string) as {
      thread_id: string
    }
    stream.push(
      eventFrame('start', { thread_id }) +
        eventFrame('delta', { thread_id, message_id: 'reply-1', text: '**首段已经显示**' }),
    )
    await flushPromises()
    expect(wrapper.text()).toContain('首段已经显示')
    expect(wrapper.get('.markdown-content strong').text()).toBe('首段已经显示')
    expect(wrapper.get('[role="status"]').text()).toContain('正在回复')
    expect(wrapper.find('[aria-label="复制回复"]').exists()).toBe(false)
    await wrapper.get('textarea').setValue('保留下一条草稿')
    stream.close()
    await flushPromises()
    expect(wrapper.text()).toContain('首段已经显示')
    expect(wrapper.get('[role="alert"]').text()).toContain('回复未完成')
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('保留下一条草稿')
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
  })
})
