/** 过程归并边界：验证工具执行记录和终止收尾，避免将未收到结果的操作显示成成功。 */
import { describe, expect, it } from 'vitest'
import { updateActivity, finishActivities } from '../activity'
import type { ChatMessage } from '../types'

/** 创建独立助手消息，验证公开函数对时间线的修改。 */
function message(): ChatMessage {
  return { id: 'assistant', role: 'assistant', blocks: [] }
}

describe('工具过程归并', () => {
  it('没有调用事件时仍能恢复执行记录，多个执行分别保存结果', () => {
    const value = message()
    updateActivity(value, {
      type: 'tool_start',
      toolCallId: 'call',
      name: 'lookup',
      kind: 'tool',
      runId: 'first',
      arguments: {},
    })
    updateActivity(value, {
      type: 'tool_start',
      toolCallId: 'call',
      name: 'lookup',
      kind: 'tool',
      runId: 'second',
      arguments: {},
    })
    updateActivity(value, {
      type: 'tool_end',
      toolCallId: 'call',
      name: 'lookup',
      kind: 'tool',
      runId: 'second',
      output: false,
    })
    expect(value.activities![0]).toMatchObject({
      status: 'running',
      runs: [
        { runId: 'first', status: 'running' },
        { runId: 'second', status: 'complete', output: false },
      ],
    })
    finishActivities(value, true)
    expect(value.activities![0]).toMatchObject({
      status: 'interrupted',
      runs: [{ status: 'interrupted' }, { status: 'complete', output: false }],
    })
  })

  it('执行前拒绝保留请求错误，不产生虚构执行记录', () => {
    const value = message()
    updateActivity(value, {
      type: 'tool_error',
      toolCallId: 'call',
      name: 'lookup',
      kind: 'tool',
      runId: null,
      message: '权限不足',
    })
    finishActivities(value, false)
    expect(value.activities).toEqual([
      expect.objectContaining({ status: 'error', error: '权限不足', runs: [] }),
    ])
  })
})
