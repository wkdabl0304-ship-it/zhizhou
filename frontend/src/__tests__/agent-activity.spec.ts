/** Agent 过程回归：以真实 SSE 消费验证状态归并、执行隔离和卡片文本安全，不调用模型或命令。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, type VueWrapper } from '@vue/test-utils'
import { useChatStore } from '@/stores/chat'
import AgentActivity from '@/components/chat/AgentActivity.vue'
import type { ToolActivity } from '@/types/chat'
import { controlledStream, eventFrame, sseResponse, success } from './helpers/chatStream'

const fetchMock = vi.fn<typeof fetch>()
const wrappers: VueWrapper[] = []

// 每例重建 Pinia 和网络替身，真实 Response/ReadableStream 保留协议到状态的完整调用路径。
beforeEach(() => {
  setActivePinia(createPinia())
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})
// 移除 DOM 和替身，不触发系统剪贴板、数据库或真实工具调用。
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  vi.unstubAllGlobals()
})

/** 从当前轮次取得全部工具卡片，测试按公开结构校验不同请求和执行的隔离。 */
function tools(): ToolActivity[] {
  return useChatStore().activeConversation!.messages[1]!.activities!.filter(
    (item): item is ToolActivity => item.type === 'tool',
  )
}

describe('Agent 过程状态', () => {
  // 同名工具依赖调用标识区分，实际执行开始前保持 queued，交错完成不能串写结果。
  it('实时累积进度正文，隔离交错执行的同名工具，并保留最终过程', async () => {
    const stream = controlledStream()
    fetchMock.mockResolvedValueOnce(stream.response)
    const chat = useChatStore()
    const pending = chat.send('比较两个城市的天气')
    const thread_id = chat.activeId!
    stream.push(
      eventFrame('start', { thread_id }) +
        eventFrame('delta', { thread_id, message_id: 'plan', text: '先查询' }) +
        eventFrame('delta', { thread_id, message_id: 'plan', text: '两个城市。' }),
    )
    await vi.waitFor(() =>
      expect(chat.activeConversation?.messages[1]?.activities?.[0]).toMatchObject({
        type: 'text',
        text: '先查询两个城市。',
        status: 'running',
      }),
    )
    expect(chat.activeConversation?.messages[1]?.blocks).toEqual([
      { type: 'paragraph', text: '先查询两个城市。' },
    ])
    expect(chat.isSending).toBe(true)
    stream.push(
      eventFrame('tool_call', {
        thread_id,
        message_id: 'plan',
        tool_call_id: 'a',
        name: 'weather',
        arguments: { city: '上海' },
      }) +
        eventFrame('tool_call', {
          thread_id,
          message_id: 'plan',
          tool_call_id: 'b',
          name: 'weather',
          arguments: { city: '北京' },
        }),
    )
    await vi.waitFor(() => expect(tools()).toHaveLength(2))
    expect(tools().map((item) => item.status)).toEqual(['queued', 'queued'])
    expect(chat.activeConversation?.messages[1]?.activities?.[0]?.status).toBe('complete')
    stream.push(
      eventFrame('tool_start', {
        thread_id,
        tool_call_id: 'a',
        run_id: 'ra',
        name: 'weather',
        kind: 'tool',
        arguments: { city: '上海' },
      }) +
        eventFrame('tool_start', {
          thread_id,
          tool_call_id: 'b',
          run_id: 'rb',
          name: 'weather',
          kind: 'tool',
          arguments: { city: '北京' },
        }) +
        eventFrame('tool_end', {
          thread_id,
          tool_call_id: 'b',
          run_id: 'rb',
          name: 'weather',
          kind: 'tool',
          output: '北京晴天',
        }),
    )
    await vi.waitFor(() =>
      expect(tools().map((item) => item.status)).toEqual(['running', 'complete']),
    )
    expect(tools()[0]?.runs[0]?.output).toBeUndefined()
    expect(tools()[1]?.runs[0]?.output).toBe('北京晴天')
    stream.push(
      eventFrame('tool_end', {
        thread_id,
        tool_call_id: 'a',
        run_id: 'ra',
        name: 'weather',
        kind: 'tool',
        output: '上海小雨',
      }) + eventFrame('done', { thread_id, message_id: 'reply', reply: '**天气对比**' }),
    )
    expect(await pending).toBe(true)
    expect(tools().map((item) => item.status)).toEqual(['complete', 'complete'])
    expect(chat.activeConversation?.messages[1]?.activities).toHaveLength(3)
    expect(chat.activeConversation?.messages[1]?.blocks).toEqual([
      { type: 'paragraph', text: '**天气对比**' },
    ])
  })

  // 一次工具失败不应终止本轮；相同请求的多次执行分别保存，执行前拒绝不伪造 run。
  it('区分命令多次执行、执行前拒绝与整轮完成', async () => {
    fetchMock.mockImplementationOnce(async (_url, init) => {
      const { thread_id } = JSON.parse(init!.body as string) as { thread_id: string }
      return sseResponse(
        [
          eventFrame('start', { thread_id }),
          eventFrame('tool_start', {
            thread_id,
            tool_call_id: 'cmd',
            run_id: 'first',
            name: 'runner',
            kind: 'command',
            arguments: 'pwd',
          }),
          eventFrame('tool_error', {
            thread_id,
            tool_call_id: 'cmd',
            run_id: 'first',
            name: 'runner',
            kind: 'command',
            message: '首次执行失败',
          }),
          eventFrame('tool_start', {
            thread_id,
            tool_call_id: 'cmd',
            run_id: 'second',
            name: 'runner',
            kind: 'command',
            arguments: { command: 'pwd' },
          }),
          eventFrame('tool_end', {
            thread_id,
            tool_call_id: 'cmd',
            run_id: 'second',
            name: 'runner',
            kind: 'command',
            output: null,
          }),
          eventFrame('tool_error', {
            thread_id,
            tool_call_id: 'rejected',
            run_id: null,
            name: 'missing',
            kind: 'tool',
            message: '未知工具',
          }),
          eventFrame('done', { thread_id, message_id: 'reply', reply: '已处理执行失败。' }),
        ].join(''),
      )
    })
    const chat = useChatStore()
    expect(await chat.send('执行任务')).toBe(true)
    expect(tools()[0]).toMatchObject({
      kind: 'command',
      status: 'complete',
      runs: [
        { runId: 'first', status: 'error', error: '首次执行失败' },
        { runId: 'second', status: 'complete', output: null },
      ],
    })
    expect(tools()[1]).toMatchObject({ status: 'error', error: '未知工具', runs: [] })
    expect(chat.activeConversation?.messages[1]?.status).toBe('complete')
  })

  // 生成失败与网络断开不能确认工具成败；先前明确完成的执行仍保留成功状态。
  it.each(['error', 'eof'])('%s 后保留进度正文和参数，未结束的执行标记未确认', async (kind) => {
    const stream = controlledStream()
    fetchMock.mockResolvedValueOnce(stream.response)
    const chat = useChatStore()
    const pending = chat.send('测试中断')
    const thread_id = chat.activeId!
    stream.push(
      eventFrame('start', { thread_id }) +
        eventFrame('tool_start', {
          thread_id,
          tool_call_id: 'active',
          run_id: 'r',
          name: 'runner',
          kind: 'command',
          arguments: 'echo test',
        }) +
        eventFrame('tool_end', {
          thread_id,
          tool_call_id: 'finished',
          run_id: 'ok',
          name: 'lookup',
          kind: 'tool',
          output: false,
        }) +
        eventFrame('delta', { thread_id, message_id: 'plan', text: '仍在整理' }),
    )
    await vi.waitFor(() => expect(chat.activeConversation?.messages[1]?.activities).toHaveLength(3))
    if (kind === 'error') stream.push(eventFrame('error', null, 50000))
    else stream.close()
    expect(await pending).toBe(false)
    expect(tools()[0]).toMatchObject({
      status: 'interrupted',
      runs: [{ status: 'interrupted', arguments: 'echo test' }],
    })
    expect(tools()[1]).toMatchObject({
      status: 'complete',
      runs: [{ status: 'complete', output: false }],
    })
    expect(chat.activeConversation?.messages[1]?.activities?.[2]).toMatchObject({
      text: '仍在整理',
      status: 'interrupted',
    })
    expect(chat.isSending).toBe(false)
  })

  // 切换到另一会话后旧连接仍可更新自身过程，不污染新会话，也不被最终回答清空。
  it('切换会话后过程仍归属原回复', async () => {
    const stream = controlledStream()
    fetchMock.mockResolvedValueOnce(stream.response)
    const chat = useChatStore()
    const pending = chat.send('旧任务')
    const oldId = chat.activeId!
    chat.startNew()
    fetchMock.mockImplementationOnce(async (_url, init) =>
      success((JSON.parse(init!.body as string) as { thread_id: string }).thread_id),
    )
    await chat.send('新任务')
    stream.push(
      eventFrame('start', { thread_id: oldId }) +
        eventFrame('delta', { thread_id: oldId, message_id: 'old', text: '旧会话进度正文' }) +
        eventFrame('done', { thread_id: oldId, message_id: 'reply', reply: '旧回答' }),
    )
    await pending
    expect(chat.activeConversation?.messages[1]?.activities).toEqual([])
    chat.select(oldId)
    expect(chat.activeConversation?.messages[1]?.activities?.[0]).toMatchObject({
      text: '旧会话进度正文',
      status: 'complete',
    })
  })

  // 最终回答只确认整轮完成，不能代替丢失的工具执行确认；前端不据此补造成功状态。
  it('done 不把缺少执行结果的请求或运行标记为成功', async () => {
    fetchMock.mockImplementationOnce(async (_url, init) => {
      const { thread_id } = JSON.parse(init!.body as string) as { thread_id: string }
      return sseResponse(
        [
          eventFrame('start', { thread_id }),
          eventFrame('tool_call', {
            thread_id,
            message_id: 'plan',
            tool_call_id: 'queued',
            name: 'lookup',
            arguments: {},
          }),
          eventFrame('tool_start', {
            thread_id,
            tool_call_id: 'running',
            run_id: 'run',
            name: 'runner',
            kind: 'command',
            arguments: 'pwd',
          }),
          eventFrame('done', { thread_id, message_id: 'reply', reply: '已有信息已整理。' }),
        ].join(''),
      )
    })
    const chat = useChatStore()
    expect(await chat.send('执行任务')).toBe(true)
    expect(tools().map((tool) => tool.status)).toEqual(['interrupted', 'interrupted'])
    expect(tools()[1]?.runs[0]?.status).toBe('interrupted')
    expect(chat.activeConversation?.messages[1]?.status).toBe('complete')
  })
})

describe('过程卡片展示', () => {
  // 工具返回内容与命令参数不能执行为 HTML；null/false/0 和多次执行都必须真实显示。
  it('折叠展示进度正文与命令详情，保留有效空值并转义不可信内容', () => {
    const wrapper = mount(AgentActivity, {
      props: {
        activities: [
          {
            id: 'thinking',
            type: 'text',
            messageId: 'm',
            text: '<script>进度正文文本</script>',
            status: 'complete',
          },
          {
            id: 'cmd',
            type: 'tool',
            toolCallId: 'cmd',
            name: 'runner',
            kind: 'command',
            status: 'complete',
            runs: [
              {
                runId: '1',
                kind: 'command',
                status: 'error',
                arguments: '<img src=x onerror=alert(1)>',
                error: '执行失败',
              },
              { runId: '2', kind: 'command', status: 'complete', arguments: 'pwd', output: null },
              { runId: '3', kind: 'command', status: 'complete', output: 0 },
              { runId: '4', kind: 'command', status: 'complete', output: false },
            ],
          },
          {
            id: 'queued',
            type: 'tool',
            toolCallId: 'queued',
            name: 'lookup',
            status: 'queued',
            arguments: {},
            runs: [],
          },
        ],
      },
    })
    wrappers.push(wrapper)
    expect(wrapper.findAll('details')).toHaveLength(2)
    expect(wrapper.get('details').attributes('open')).toBeUndefined()
    expect(wrapper.text()).toContain('<script>进度正文文本</script>')
    expect(wrapper.text()).toContain('命令执行')
    expect(wrapper.text()).toContain('第 2 次执行')
    expect(wrapper.text()).toContain('已请求，等待执行')
    expect(wrapper.findAll('pre').map((node) => node.text())).toEqual(
      expect.arrayContaining(['null', '0', 'false', 'pwd']),
    )
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.find('img').exists()).toBe(false)
  })
})
