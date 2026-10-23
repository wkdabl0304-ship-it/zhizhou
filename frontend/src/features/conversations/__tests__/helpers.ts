/** 会话测试契约数据：公开目录和轮次均为虚构，不使用真实数据库或模型。 */
export { response, deferredResponse } from '@/__tests__/helpers/http'
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
