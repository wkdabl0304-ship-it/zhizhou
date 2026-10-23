/** 公开事件解码：直接验证共享字段边界，实时流与历史必须得到一致的安全事件。 */
import { describe, expect, it } from 'vitest'
import { decodeEvent } from '../../api/events'

const tool = { tool_call_id: 'call', name: 'lookup', run_id: 'run', kind: 'tool' }

describe('公开事件字段', () => {
  it('保留正文和最终回答标识，允许空增量但拒绝空标识', () => {
    expect(decodeEvent('delta', { message_id: 'message', text: '' })).toEqual({
      type: 'delta',
      messageId: 'message',
      text: '',
    })
    expect(decodeEvent('done', { message_id: 'message', reply: '完成' })).toMatchObject({
      reply: '完成',
    })
    expect(() => decodeEvent('delta', { message_id: ' ', text: '内容' })).toThrow(/聊天/)
  })

  it('允许嵌套 JSON 参数及 null、false、0 等工具结果', () => {
    const arguments_ = { nested: [null, false, 0, { value: '内容' }] }
    expect(
      decodeEvent('tool_call', { ...tool, message_id: 'message', arguments: arguments_ }),
    ).toMatchObject({ arguments: arguments_ })
    for (const output of [null, false, 0, '', arguments_])
      expect(decodeEvent('tool_end', { ...tool, output })).toMatchObject({ output })
    expect(decodeEvent('tool_start', { ...tool, kind: 'command', arguments: 'pwd' })).toMatchObject(
      { kind: 'command', arguments: 'pwd' },
    )
  })

  it.each([
    ['tool_call', { ...tool, message_id: 'm', arguments: [] }],
    ['tool_call', { ...tool, message_id: 'm', arguments: { invalid: undefined } }],
    ['tool_start', { ...tool, arguments: null }],
    ['tool_start', { ...tool, kind: 'unknown', arguments: {} }],
    ['tool_end', { ...tool, output: Number.POSITIVE_INFINITY }],
    ['tool_end', { ...tool, run_id: '', output: '结果' }],
    ['tool_error', { ...tool, message: '' }],
  ])('拒绝损坏工具事件 %#', (event, data) => {
    expect(() => decodeEvent(event as string, data as Record<string, unknown>)).toThrow(/聊天/)
  })

  it('执行前拒绝不伪造 runId，未知事件不能成为展示内容', () => {
    expect(decodeEvent('tool_error', { ...tool, run_id: null, message: '拒绝执行' })).toMatchObject(
      { runId: null, message: '拒绝执行' },
    )
    expect(() => decodeEvent('reasoning_delta', { text: '内部内容' })).toThrow(/聊天/)
  })
})
