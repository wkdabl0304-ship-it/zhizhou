/** 通用 SSE 支撑回归：保证任意事件不被注入聊天字段，并按原始字节交付。 */
import { describe, expect, it } from 'vitest'
import { controlledStream, eventFrame } from '../vitest/sse'

describe('通用 SSE 替身', () => {
  it('保留任意事件数据，不追加身份、会话或统一业务信封', () => {
    expect(eventFrame('start', { progress: 0 })).toBe('event: start\ndata: {"progress":0}\n\n')
    expect(eventFrame('notice', null)).toBe('event: notice\ndata: null\n\n')
  })

  it('逐块交付多字节内容，正常结束后读到完成状态', async () => {
    const stream = controlledStream()
    const reader = stream.response.body!.getReader()
    const bytes = new TextEncoder().encode('舟')
    stream.push(bytes.subarray(0, 1))
    expect((await reader.read()).value).toEqual(bytes.subarray(0, 1))
    stream.push(bytes.subarray(1))
    expect((await reader.read()).value).toEqual(bytes.subarray(1))
    stream.close()
    expect((await reader.read()).done).toBe(true)
    reader.releaseLock()
  })
})
