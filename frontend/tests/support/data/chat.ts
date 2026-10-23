/** 会话测试契约数据：公开目录和轮次均为虚构，不使用真实数据库或模型。 */
export const A = '00000000-0000-4000-8000-000000000001'
export const B = '00000000-0000-4000-8000-000000000002'

/** 创建固定时间的目录条目，测试可按需覆盖标题和最近消息时间。 */
export function info(id = A, title = '历史话题', at = '2026-10-23T08:00:00Z') {
  return { conversation_id: id, title, created_at: at, last_message_at: at }
}
/** 创建完整历史轮次；异常状态和公开事件由各回归场景显式覆盖。 */
export function turn(seq = 1, status = 'completed') {
  return {
    turn_id: `turn-${seq}`,
    seq,
    user_content: `问题${seq}`,
    assistant_content: status === 'completed' ? `**回答${seq}**` : null,
    assistant_message_id: status === 'completed' ? `answer-${seq}` : null,
    public_events: [],
    status,
    error_code: null,
    created_at: '2026-10-23T08:00:00Z',
    updated_at: '2026-10-23T08:00:01Z',
    finished_at: status === 'running' ? null : '2026-10-23T08:00:01Z',
  }
}

/** 为聊天事件提供独立契约数据，损坏协议的用例仍可显式覆盖默认字段。 */
export function chatEventData(event: string, data: unknown): unknown {
  return event === 'start' && data && typeof data === 'object'
    ? { turn_id: 'test-turn', is_new: true, ...data }
    : data
}

/** 创建成功轮次的独立场景数据，避免跨用例共享计数器和可变消息。 */
export function completedChatEvents(
  conversationId: string,
  reply: string,
  isNew: boolean,
): Array<[string, unknown]> {
  const message_id = 'reply-1'
  return [
    [
      'start',
      {
        conversation_id: conversationId,
        turn_id: `server-turn-${crypto.randomUUID()}`,
        is_new: isNew,
      },
    ],
    ['delta', { conversation_id: conversationId, message_id, text: reply }],
    ['done', { conversation_id: conversationId, message_id, reply }],
  ]
}
