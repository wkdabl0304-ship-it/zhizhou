/** SSE 传输回归：验证真实字节流的拆包、UTF-8、事件顺序和 reader 清理，不启动外部服务。 */
import { createTestPinia as createPinia } from '@tests/support/vitest/mount'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { streamChatMessage, type ChatStreamEvent } from '@/features/chat/api/stream'
import { controlledStream, sseResponse } from '@tests/support/vitest/sse'
import { eventFrame } from '@tests/support/vitest/chat'
import { disposePinia, type Pinia } from 'pinia'
import { authenticate } from '@tests/support/vitest/auth'
let pinia: Pinia

const fetchMock = vi.fn<typeof fetch>()
const conversation_id = 'test-thread'
const message_id = 'reply-1'

// 每个用例重置网络替身；Response/ReadableStream 使用真实实现以覆盖分帧过程。
beforeEach(async () => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  pinia = createPinia()
  await authenticate(pinia, fetchMock)
})
// 撤销网络替身，不影响其他文件中的页面请求。
afterEach(() => {
  disposePinia(pinia)
  vi.unstubAllGlobals()
})

/** 收集一轮聊天的全部业务事件供协议断言使用；完整消费生成器，解析失败继续向测试传播。 */
async function collect(): Promise<ChatStreamEvent[]> {
  const events: ChatStreamEvent[] = []
  for await (const event of streamChatMessage('测试消息', conversation_id)) events.push(event)
  return events
}

describe('POST SSE 解析', () => {
  // 轮次信息和 is_new 必须与请求一致，不允许错误 start 把新输入绑定到其他业务上下文。
  it.each([
    { turn_id: null, is_new: false },
    { turn_id: 'turn', is_new: true },
    { turn_id: 'turn', is_new: 'false' },
  ])('拒绝损坏的 start 元数据 %#', async (data) => {
    fetchMock.mockResolvedValueOnce(sseResponse(eventFrame('start', { conversation_id, ...data })))
    await expect(collect()).rejects.toThrow('聊天开始事件轮次无效')
  })

  // 每字节拆包同时覆盖中文多字节、JSON 与 CRLF 边界，避免把网络块误认为事件。
  it.each(['\n', '\r\n', '\r'])('兼容 %j 换行、注释、多行 data 和 UTF-8 拆包', async (newline) => {
    const stream = controlledStream()
    fetchMock.mockResolvedValueOnce(stream.response)
    const multiline = JSON.stringify(
      { code: 0, data: { conversation_id, message_id, text: '你好🌊\n第二行' } },
      null,
      2,
    )
      .split('\n')
      .map((line) => `data: ${line}`)
      .join('\n')
    const wire = (
      ': 心跳\nid: ignored\nretry: 1000\n\n' +
      eventFrame('start', { conversation_id, is_new: false }) +
      `event: delta\n${multiline}\n\n` +
      eventFrame('done', { conversation_id, message_id, reply: '最终回答' })
    )
      .split('\n')
      .join(newline)
    const pending = collect()
    for (const byte of new TextEncoder().encode(wire)) stream.push(new Uint8Array([byte]))
    // CR 单独作为末尾换行时，EOF 才能确认它不是下一块 CRLF 的前半段。
    stream.close()
    expect(await pending).toEqual([
      { type: 'start', conversationId: conversation_id, turnId: 'test-turn', isNew: false },
      { type: 'delta', messageId: message_id, text: '你好🌊\n第二行' },
      { type: 'done', messageId: message_id, reply: '最终回答' },
    ])
  })

  // 不关闭服务端流；第一段必须先交付，done 到达后应主动结束读取并取消响应体。
  it('首段早于 done 交付，完成后释放保持打开的连接', async () => {
    const stream = controlledStream()
    fetchMock.mockResolvedValueOnce(stream.response)
    const events = streamChatMessage('测试', conversation_id)
    stream.push(eventFrame('start', { conversation_id, is_new: false }))
    expect((await events.next()).value).toEqual({
      type: 'start',
      conversationId: conversation_id,
      turnId: 'test-turn',
      isNew: false,
    })
    stream.push(eventFrame('delta', { conversation_id, message_id, text: '第一段' }))
    expect((await events.next()).value).toEqual({
      type: 'delta',
      messageId: message_id,
      text: '第一段',
    })
    stream.push(eventFrame('done', { conversation_id, message_id, reply: '完整回复' }))
    expect((await events.next()).value).toMatchObject({ type: 'done', reply: '完整回复' })
    expect((await events.next()).done).toBe(true)
    expect(stream.isCancelled()).toBe(true)
  })

  // 消费者主动结束迭代时必须取消底层读取，给后端触发断开清理的机会。
  it('提前退出消费会关闭流', async () => {
    const stream = controlledStream()
    fetchMock.mockResolvedValueOnce(stream.response)
    stream.push(eventFrame('start', { conversation_id, is_new: false }))
    for await (const event of streamChatMessage('测试', conversation_id)) {
      expect(event.type).toBe('start')
      break
    }
    expect(stream.isCancelled()).toBe(true)
  })

  // 没有可见增量也允许 done 返回完整回答，例如最终文本仅由图完成结果给出。
  it('支持没有 delta 的完整回答', async () => {
    fetchMock.mockResolvedValueOnce(
      sseResponse(
        eventFrame('start', { conversation_id, is_new: false }) +
          eventFrame('done', { conversation_id, message_id, reply: '仅最终文本' }),
      ),
    )
    expect(await collect()).toHaveLength(2)
  })

  // 推理事件已从公开协议移除，即使字段完整也不能作为正文交给展示层。
  it('拒绝旧的推理事件，不把推理解释为进度正文', async () => {
    fetchMock.mockResolvedValueOnce(
      sseResponse(
        eventFrame('start', { conversation_id, is_new: false }) +
          eventFrame('reasoning_delta', { conversation_id, message_id, text: '内部推理' }),
      ),
    )
    await expect(collect()).rejects.toThrow(/聊天/)
  })

  // 传输完成与业务完成不同；协议错误和被截断的终止帧都应失败，不能误判为成功。
  it.each([
    'missing-start',
    'duplicate-start',
    'missing-done',
    'truncated-done',
    'wrong-thread',
    'wrong-message',
    'invalid-json',
    'unknown-event',
    'business-code',
    'wrong-content-type',
    'http-error',
  ])('%s 不得作为成功响应', async (kind) => {
    const start = eventFrame('start', { conversation_id, is_new: false })
    const done = eventFrame('done', { conversation_id, message_id, reply: '最终回答' })
    let text = start
    if (kind === 'missing-start') text = done
    if (kind === 'duplicate-start') text += start
    if (kind === 'truncated-done') text += done.trimEnd()
    if (kind === 'wrong-thread')
      text += eventFrame('delta', { conversation_id: 'other', message_id, text: '串线' })
    if (kind === 'wrong-message')
      text += eventFrame('delta', { conversation_id, message_id: '', text: '无标识' })
    if (kind === 'invalid-json') text += 'event: delta\ndata: {\n\n'
    if (kind === 'unknown-event') text += eventFrame('other', { conversation_id, message_id })
    if (kind === 'business-code')
      text += eventFrame('delta', { conversation_id, message_id, text: '失败' }, 50000)
    fetchMock.mockResolvedValueOnce(
      kind === 'wrong-content-type'
        ? new Response('{}')
        : kind === 'http-error'
          ? new Response('{}', { status: 422 })
          : sseResponse(text),
    )
    await expect(collect()).rejects.toThrow(
      kind === 'invalid-json'
        ? /JSON/
        : kind === 'http-error'
          ? /服务响应/
          : kind === 'business-code'
            ? /生成失败/
            : /聊天/,
    )
  })

  // error 为终止事件且 data=null；客户端应立即停止读取，不必等待后端关闭连接。
  it('流内 error 后取消响应体并抛出异常', async () => {
    const stream = controlledStream()
    fetchMock.mockResolvedValueOnce(stream.response)
    stream.push(
      eventFrame('start', { conversation_id, is_new: false }) + eventFrame('error', null, 50000),
    )
    await expect(collect()).rejects.toThrow('生成失败')
    expect(stream.isCancelled()).toBe(true)
  })

  // 实际执行事件没有 message_id；工具局部失败使用 code=0，不得终止整轮事件消费。
  it('消费进度正文、请求、命令执行与局部失败事件，直到最终回答', async () => {
    fetchMock.mockResolvedValueOnce(
      sseResponse(
        [
          eventFrame('start', { conversation_id, is_new: false }),
          eventFrame('delta', { conversation_id, message_id, text: '先读取工作目录。' }),
          eventFrame('tool_call', {
            conversation_id,
            message_id,
            tool_call_id: 'call-1',
            name: 'runner',
            arguments: { command: 'pwd' },
          }),
          eventFrame('tool_start', {
            conversation_id,
            tool_call_id: 'call-1',
            run_id: 'run-1',
            name: 'runner',
            kind: 'command',
            arguments: 'pwd',
          }),
          eventFrame('tool_error', {
            conversation_id,
            tool_call_id: 'call-1',
            run_id: 'run-1',
            name: 'runner',
            kind: 'command',
            message: '执行失败，请稍后重试',
          }),
          eventFrame('tool_error', {
            conversation_id,
            tool_call_id: 'rejected',
            run_id: null,
            name: 'unknown',
            kind: 'tool',
            message: '工具不可用',
          }),
          eventFrame('tool_end', {
            conversation_id,
            tool_call_id: 'other',
            run_id: 'run-2',
            name: 'lookup',
            kind: 'tool',
            output: { value: null, ok: false, count: 0, items: [] },
          }),
          eventFrame('done', { conversation_id, message_id, reply: '已整理现有信息。' }),
        ].join(''),
      ),
    )
    expect(await collect()).toEqual([
      { type: 'start', conversationId: conversation_id, turnId: 'test-turn', isNew: false },
      { type: 'delta', messageId: message_id, text: '先读取工作目录。' },
      {
        type: 'tool_call',
        messageId: message_id,
        toolCallId: 'call-1',
        name: 'runner',
        arguments: { command: 'pwd' },
      },
      {
        type: 'tool_start',
        toolCallId: 'call-1',
        runId: 'run-1',
        name: 'runner',
        kind: 'command',
        arguments: 'pwd',
      },
      {
        type: 'tool_error',
        toolCallId: 'call-1',
        runId: 'run-1',
        name: 'runner',
        kind: 'command',
        message: '执行失败，请稍后重试',
      },
      {
        type: 'tool_error',
        toolCallId: 'rejected',
        runId: null,
        name: 'unknown',
        kind: 'tool',
        message: '工具不可用',
      },
      {
        type: 'tool_end',
        toolCallId: 'other',
        runId: 'run-2',
        name: 'lookup',
        kind: 'tool',
        output: { value: null, ok: false, count: 0, items: [] },
      },
      { type: 'done', messageId: message_id, reply: '已整理现有信息。' },
    ])
  })

  // 新事件也必须校验会话、调用标识及字段类型；协议损坏不能悄悄归并到其他卡片。
  it.each([
    ['delta', { message_id, text: 123 }],
    ['tool_call', { message_id, tool_call_id: 'id', name: 'lookup', arguments: [] }],
    ['tool_start', { tool_call_id: 'id', name: 'lookup', kind: 'tool', run_id: '', arguments: {} }],
    [
      'tool_start',
      { tool_call_id: 'id', name: 'lookup', kind: 'shell', run_id: 'run', arguments: {} },
    ],
    ['tool_end', { tool_call_id: 'id', name: 'lookup', kind: 'tool', run_id: 'run' }],
    [
      'tool_error',
      { tool_call_id: 'id', name: 'lookup', kind: 'tool', run_id: null, message: 123 },
    ],
    [
      'tool_start',
      {
        tool_call_id: 'id',
        name: 'lookup',
        kind: 'tool',
        run_id: 'run',
        arguments: {},
        conversation_id: 'wrong',
      },
    ],
  ])('拒绝不合法的 %s 过程事件', async (type, data) => {
    fetchMock.mockResolvedValueOnce(
      sseResponse(
        eventFrame('start', { conversation_id, is_new: false }) +
          eventFrame(type, { conversation_id, ...data }),
      ),
    )
    await expect(collect()).rejects.toThrow(/聊天/)
  })
})
