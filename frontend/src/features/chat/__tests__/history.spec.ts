/** 历史展示转换：验证轮次标识、状态和最终回答分离，避免刷新后改变已公开的含义。 */
import { describe, expect, it } from 'vitest'
import { turnMessages } from '../history'
import type { HistoryTurn } from '../api/conversations'

/** 创建独立的已校验轮次，单例只覆盖当前测试需要的状态和事件。 */
function turn(overrides: Partial<HistoryTurn> = {}): HistoryTurn {
  return {
    turn_id: 'turn',
    seq: 1,
    user_content: '问题',
    assistant_content: '最终回答',
    assistant_message_id: 'final',
    status: 'completed',
    events: [],
    ...overrides,
  }
}

describe('历史轮次到展示消息', () => {
  it('未产生输出的失败轮次不显示模型切换，已有正文或完成的历史保留切换依据', () => {
    expect(
      turnMessages(turn({ status: 'failed', assistant_content: null, events: [] }))[0]!
        .modelReplyStarted,
    ).toBe(false)
    expect(
      turnMessages(
        turn({
          status: 'failed',
          assistant_content: null,
          events: [{ type: 'delta', messageId: 'partial', text: '已有正文' }],
        }),
      )[0]!.modelReplyStarted,
    ).toBe(true)
    expect(turnMessages(turn())[0]!.modelReplyStarted).toBe(true)
  })
  it('使用稳定轮次 ID，最终正文按标识分离而非按内容删除', () => {
    const source = turn({
      events: [
        { type: 'delta', messageId: 'plan', text: '最终回答' },
        { type: 'delta', messageId: 'final', text: '临时片段' },
      ],
    })
    const messages = turnMessages(source)
    expect(messages.map((message) => message.id)).toEqual(['turn-user', 'turn-assistant'])
    expect(turnMessages(source).map((message) => message.id)).toEqual(
      messages.map((message) => message.id),
    )
    expect(messages[1]).toMatchObject({
      status: 'complete',
      blocks: [{ type: 'paragraph', text: '最终回答' }],
    })
    expect(messages[1]!.activities).toEqual([
      expect.objectContaining({ messageId: 'plan', text: '最终回答' }),
    ])
    expect(source.events).toHaveLength(2)
  })

  it.each(['running', 'failed', 'interrupted'] as const)(
    '恢复 %s 状态并保留未完成过程',
    (status) => {
      const messages = turnMessages(
        turn({
          status,
          assistant_content: null,
          assistant_message_id: null,
          events: [
            { type: 'delta', messageId: 'partial', text: '已收到内容' },
            {
              type: 'tool_start',
              toolCallId: 'call',
              runId: 'run',
              name: 'lookup',
              kind: 'tool',
              arguments: {},
            },
          ],
        }),
      )
      expect(messages[1]).toMatchObject({ status: 'error', blocks: [], error: expect.any(String) })
      expect(messages[1]!.activities).toEqual([
        expect.objectContaining({ text: '已收到内容', status: 'complete' }),
        expect.objectContaining({
          status: 'interrupted',
          runs: [expect.objectContaining({ status: 'interrupted' })],
        }),
      ])
    },
  )

  it('中断时仅将仍在接收的正文标记为未完成', () => {
    const messages = turnMessages(
      turn({
        status: 'interrupted',
        assistant_content: null,
        assistant_message_id: null,
        events: [
          {
            type: 'tool_start',
            toolCallId: 'call',
            runId: 'run',
            name: 'lookup',
            kind: 'tool',
            arguments: {},
          },
          { type: 'delta', messageId: 'partial', text: '仍在接收' },
        ],
      }),
    )
    expect(messages[1]!.activities).toContainEqual(
      expect.objectContaining({ text: '仍在接收', status: 'interrupted' }),
    )
  })
})
