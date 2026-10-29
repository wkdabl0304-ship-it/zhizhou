/** 工作空间集成回归：验证示例填入、发送后的焦点和会话切换；不连接网络或数据库。 */
import { createTestPinia as createPinia } from '@tests/support/vitest/mount'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { disposePinia, type Pinia } from 'pinia'
import { useChatStore } from '@/features/chat/store'
import { useModelConfigStore } from '@/features/model-config/store'
import { modelConfigData } from '@tests/support/data/model-config'
import { authenticate } from '@tests/support/vitest/auth'
let pinia: Pinia
let serverSequence = 0
import { defineComponent } from 'vue'
import { TooltipProvider } from 'reka-ui'
import { RouterView, createMemoryHistory } from 'vue-router'
import { createAppRouter } from '@/router'
import WelcomeHeading from '@/features/chat/components/WelcomeHeading.vue'
import { controlledStream } from '@tests/support/vitest/sse'
import { eventFrame, success, withModelOptions } from '@tests/support/vitest/chat'

const wrappers: VueWrapper[] = []
const fetchMock = vi.fn<typeof fetch>()
// jsdom 没有真实视口断点；桌面替身只提供组件实际使用的媒体查询监听接口。
beforeEach(async () => {
  fetchMock.mockReset()
  // 回显实际 conversation_id，验证页面经过真实 API 适配层更新消息，替身不连接模型。
  fetchMock.mockImplementation(async (_url, init) => {
    const { conversation_id } = JSON.parse(init!.body as string) as { conversation_id?: string }
    return success(
      conversation_id ?? `server-${++serverSequence}`,
      '来自后端的回复',
      !conversation_id,
    )
  })
  vi.stubGlobal('fetch', withModelOptions(fetchMock))
  pinia = createPinia()
  await authenticate(pinia, fetchMock)
  // 本组聚焦聊天生成，预置有效默认；首次默认加载与配置引导由跨业务集成测试验证。
  useModelConfigStore(pinia).selected = modelConfigData().selected
  // 此组聚焦流式交互，使用已加载的空目录；真实首次目录读取另由会话页面集成测试覆盖。
  useChatStore(pinia).listInitialized = true
  vi.stubGlobal('matchMedia', () => ({
    matches: false,
    addEventListener: vi.fn<() => void>(),
    removeEventListener: vi.fn<() => void>(),
  }))
})
// 卸载组件后再恢复全局替身，确保监听清理调用仍能访问原替身。
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  disposePinia(pinia)
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

/** 挂载真实路由及共用工作区，以独立 Pinia 和提示上下文验证聊天页面级交互。 */
async function renderWorkspace() {
  const router = createAppRouter(createMemoryHistory())
  await router.push('/')
  await router.isReady()
  const Host = defineComponent({
    components: { TooltipProvider, RouterView },
    template: '<TooltipProvider><RouterView /></TooltipProvider>',
  })
  const wrapper = mount(Host, {
    attachTo: document.body,
    global: { plugins: [pinia, router] },
  })
  wrappers.push(wrapper)
  await flushPromises()
  return wrapper
}

describe('聊天工作空间', () => {
  // 首页输入实例会在发送时被替换，必须将焦点送到新对话页的输入框。
  it('首页移除示例，输入草稿后发送创建对话并保持输入焦点', async () => {
    const wrapper = await renderWorkspace()
    // 首页使用独立的现代宋体组件，正文与输入区继续使用公共无衬线字体。
    expect(wrapper.findComponent(WelcomeHeading).exists()).toBe(true)
    // 装饰跟随首页生命周期，进入正文后应释放背景，保持阅读区稳定。
    expect(wrapper.find('.river-backdrop').exists()).toBe(true)
    expect(wrapper.find('.suggestion').exists()).toBe(false)
    await wrapper.get('textarea').setValue('帮我整理入职清单')
    expect(wrapper.findAll('article')).toHaveLength(0)
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toContain('入职清单')
    await wrapper.get('form.chat-composer').trigger('submit')
    await flushPromises()
    expect(wrapper.findAll('article')).toHaveLength(2)
    expect(wrapper.find('.river-backdrop').exists()).toBe(false)
    expect(document.activeElement).toBe(wrapper.get('textarea').element)
    expect(wrapper.text()).toContain('来自后端的回复')
    expect(wrapper.text()).not.toContain('演示回复')
  })

  // 草稿不跨会话携带，防止切换后误发；会话正文仍由各自数据恢复。
  it('切换会话与新建时清除草稿', async () => {
    const wrapper = await renderWorkspace()
    await wrapper.get('textarea').setValue('第一段对话')
    await wrapper.get('form.chat-composer').trigger('submit')
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
    const wrapper = await renderWorkspace()
    await wrapper.get('textarea').setValue('测试慢请求')
    await wrapper.get('form.chat-composer').trigger('submit')
    expect(wrapper.get('[role="status"]').text()).toContain('正在整理思路')
    expect(document.activeElement).toBe(wrapper.get('textarea').element)
    await wrapper.get('textarea').setValue('下一条草稿')
    expect(wrapper.get('.chat-composer button[type="submit"]').attributes('disabled')).toBeDefined()
    await wrapper.get('textarea').trigger('keydown', { key: 'Enter' })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('下一条草稿')
    rejectReply(new TypeError('Failed to fetch'))
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('暂时无法获取回复')
    expect(
      wrapper.get('.chat-composer button[type="submit"]').attributes('disabled'),
    ).toBeUndefined()
    await wrapper.get('form.chat-composer').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('来自后端的回复')
  })

  // 在流未完成时检查实际 DOM，确保增量可见、复制暂不可用，中断后仍保留部分正文。
  it('逐段展示回复，中断后保留文本和草稿并标明未完成', async () => {
    const stream = controlledStream()
    fetchMock.mockResolvedValueOnce(stream.response)
    const wrapper = await renderWorkspace()
    await wrapper.get('textarea').setValue('流式回复测试')
    await wrapper.get('form.chat-composer').trigger('submit')
    const { conversation_id = 'server-session-a' } = JSON.parse(
      fetchMock.mock.calls[0]![1]!.body as string,
    ) as {
      conversation_id: string
    }
    stream.push(
      eventFrame('start', { conversation_id }) +
        eventFrame('delta', { conversation_id, message_id: 'reply-1', text: '**首段已经显示**' }),
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
    expect(
      wrapper.get('.chat-composer button[type="submit"]').attributes('disabled'),
    ).toBeUndefined()
  })

  // 贯通 SSE → store → 过程卡片：工具失败后仍等待最终回答，复制最终正文不包含进度正文或工具输出。
  it('实时展示进度正文和命令过程，局部失败后继续展示 Markdown 回答', async () => {
    const stream = controlledStream()
    fetchMock.mockResolvedValueOnce(stream.response)
    const wrapper = await renderWorkspace()
    await wrapper.get('textarea').setValue('执行测试任务')
    await wrapper.get('form.chat-composer').trigger('submit')
    const { conversation_id = 'server-session-a' } = JSON.parse(
      fetchMock.mock.calls[0]![1]!.body as string,
    ) as {
      conversation_id: string
    }
    stream.push(
      eventFrame('start', { conversation_id }) +
        eventFrame('delta', {
          conversation_id,
          message_id: 'plan',
          text: '模型实际提供的进度正文文本',
        }),
    )
    await flushPromises()
    expect(wrapper.get('[aria-label="执行过程"]').text()).toContain('模型实际提供的进度正文文本')
    expect(wrapper.get('[role="status"]').text()).toContain('正在回复')
    stream.push(
      eventFrame('tool_start', {
        conversation_id,
        tool_call_id: 'cmd',
        run_id: 'run',
        name: 'runner',
        kind: 'command',
        arguments: 'pwd',
      }),
    )
    await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toContain('正在执行命令')
    expect(wrapper.get('[aria-label="执行过程"]').text()).toContain('命令执行')
    stream.push(
      eventFrame('tool_error', {
        conversation_id,
        tool_call_id: 'cmd',
        run_id: 'run',
        name: 'runner',
        kind: 'command',
        message: '工具执行失败',
      }),
    )
    await flushPromises()
    expect(wrapper.find('.message > .ui-feedback').exists()).toBe(false)
    await wrapper.get('textarea').setValue('下一条草稿')
    expect(wrapper.get('.chat-composer button[type="submit"]').attributes('disabled')).toBeDefined()
    stream.push(eventFrame('done', { conversation_id, message_id: 'reply', reply: '**最终回答**' }))
    await flushPromises()
    expect(wrapper.get('.markdown-content strong').text()).toBe('最终回答')
    expect(wrapper.get('[aria-label="执行过程"]').text()).toContain('工具执行失败')
    expect(
      wrapper.get('.chat-composer button[type="submit"]').attributes('disabled'),
    ).toBeUndefined()
    const writeText = vi.fn<(text: string) => Promise<void>>().mockResolvedValue()
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    await wrapper.get('[aria-label="复制回复"]').trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith('**最终回答**')
  })

  // 贯通正文→工具→后续正文→工具→最终回答；验证实时顺序、自动折叠与完整展开。
  it('按顺序显示行动和工具，完成后折叠全部过程且不重复最终回答', async () => {
    const stream = controlledStream()
    fetchMock.mockResolvedValueOnce(stream.response)
    const wrapper = await renderWorkspace()
    await wrapper.get('textarea').setValue('查询北京天气')
    await wrapper.get('form.chat-composer').trigger('submit')
    const { conversation_id = 'server-session-a' } = JSON.parse(
      fetchMock.mock.calls[0]![1]!.body as string,
    ) as {
      conversation_id: string
    }
    stream.push(
      [
        eventFrame('start', { conversation_id }),
        eventFrame('delta', { conversation_id, message_id: 'first', text: '我先查询北京天气。' }),
        eventFrame('tool_call', {
          conversation_id,
          message_id: 'first',
          tool_call_id: 'weather',
          name: 'get_weather',
          arguments: { city: '北京' },
        }),
        eventFrame('tool_start', {
          conversation_id,
          tool_call_id: 'weather',
          run_id: 'r1',
          name: 'get_weather',
          kind: 'tool',
          arguments: { city: '北京' },
        }),
        eventFrame('tool_end', {
          conversation_id,
          tool_call_id: 'weather',
          run_id: 'r1',
          name: 'get_weather',
          kind: 'tool',
          output: '晴天',
        }),
        eventFrame('delta', { conversation_id, message_id: 'next', text: '我接着核对温度。' }),
        eventFrame('tool_call', {
          conversation_id,
          message_id: 'next',
          tool_call_id: 'temperature',
          name: 'check_temperature',
          arguments: {},
        }),
        eventFrame('tool_start', {
          conversation_id,
          tool_call_id: 'temperature',
          run_id: 'r2',
          name: 'check_temperature',
          kind: 'tool',
          arguments: {},
        }),
        eventFrame('tool_end', {
          conversation_id,
          tool_call_id: 'temperature',
          run_id: 'r2',
          name: 'check_temperature',
          kind: 'tool',
          output: '25°C',
        }),
        // 同文不同标识必须保留，不能靠字符串去重误删进度；done 会替换最终消息的增量。
        eventFrame('delta', { conversation_id, message_id: 'answer', text: '我接着核对温度。' }),
      ].join(''),
    )
    await flushPromises()
    const timeline = wrapper.get('.process-timeline')
    expect(timeline.isVisible()).toBe(true)
    expect(wrapper.find('.process-toggle').exists()).toBe(false)
    expect(wrapper.findAll('.process-entry').map((item) => item.text())).toEqual([
      '我先查询北京天气。',
      expect.stringContaining('get_weather'),
      '我接着核对温度。',
      expect.stringContaining('check_temperature'),
      '我接着核对温度。',
    ])
    // 工具详情是独立原生折叠，整体收起后再次展开应保留用户先前的选择。
    wrapper.get('details').element.setAttribute('open', '')
    stream.push(
      eventFrame('done', { conversation_id, message_id: 'answer', reply: '**北京晴天，25°C。**' }),
    )
    await flushPromises()
    expect(wrapper.get('.process-toggle').attributes('aria-expanded')).toBe('false')
    expect(timeline.isVisible()).toBe(false)
    expect(wrapper.get('.message--assistant .message-body').text()).toBe('北京晴天，25°C。')
    expect(wrapper.findAll('.process-entry')).toHaveLength(4)
    await wrapper.get('.process-toggle').trigger('click')
    expect(timeline.isVisible()).toBe(true)
    expect(wrapper.get('details').attributes('open')).toBe('')
    expect(
      wrapper.findAll('.process-entry').filter((item) => item.text() === '我接着核对温度。'),
    ).toHaveLength(1)
    expect(timeline.text()).not.toContain('北京晴天，25°C。')
    // 与最终事件无关的草稿更新不应再次强制折叠。
    await wrapper.get('textarea').setValue('下一条问题')
    expect(timeline.isVisible()).toBe(true)
    await wrapper.get('.process-toggle').trigger('click')
    expect(timeline.isVisible()).toBe(false)
  })

  // 单纯聊天没有工具过程；最终回答的消息增量移出时间线，不留下空的折叠入口。
  it('普通回答完成后只展示最终正文，失败时保留展开的部分过程', async () => {
    const stream = controlledStream()
    fetchMock.mockResolvedValueOnce(stream.response)
    const wrapper = await renderWorkspace()
    await wrapper.get('textarea').setValue('你好')
    await wrapper.get('form.chat-composer').trigger('submit')
    const { conversation_id = 'server-session-a' } = JSON.parse(
      fetchMock.mock.calls[0]![1]!.body as string,
    ) as {
      conversation_id: string
    }
    stream.push(
      eventFrame('start', { conversation_id }) +
        eventFrame('delta', { conversation_id, message_id: 'answer', text: '你好' }) +
        eventFrame('done', { conversation_id, message_id: 'answer', reply: '你好。' }),
    )
    await flushPromises()
    expect(wrapper.find('.agent-activity').exists()).toBe(false)
    expect(wrapper.get('.message--assistant .message-body').text()).toBe('你好。')

    const failed = controlledStream()
    fetchMock.mockResolvedValueOnce(failed.response)
    await wrapper.get('textarea').setValue('继续')
    await wrapper.get('form.chat-composer').trigger('submit')
    failed.push(
      eventFrame('start', { conversation_id, turn_id: 'second-turn', is_new: false }) +
        eventFrame('delta', { conversation_id, message_id: 'partial', text: '我先检查。' }),
    )
    failed.close()
    await flushPromises()
    expect(wrapper.get('.process-toggle').attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('.process-timeline').isVisible()).toBe(true)
    expect(wrapper.get('.process-timeline').text()).toBe('我先检查。')
    expect(wrapper.get('[role="alert"]').text()).toContain('回复未完成')
  })
})
