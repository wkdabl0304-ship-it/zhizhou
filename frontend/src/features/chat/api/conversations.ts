/** 会话接口：验证服务端目录、轮次和公开过程，游标原样传回，不读取模型 checkpoint。 */
import { authenticatedFetch, readEnvelope, ApiError } from '@/features/auth/authenticated'
import { decodeEvent } from './events'
import type { ChatStreamEvent } from '@/features/chat/chat-events'

/** 服务端会话元数据，用于排序与侧栏展示。 */
export interface ConversationInfo {
  conversation_id: string
  title: string
  created_at: string
  last_message_at: string
}
/** 公开历史轮次；过程已转成与 SSE 相同的展示事件。 */
export interface HistoryTurn {
  turn_id: string
  seq: number
  user_content: string
  assistant_content: string | null
  assistant_message_id: string | null
  status: 'running' | 'completed' | 'failed' | 'interrupted'
  events: Exclude<ChatStreamEvent, { type: 'start' }>[]
}
/** 判断未知 JSON 是否为对象，排除 null 和数组。 */
function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}
/** 验证目录字段，禁止损坏的 ID、时间或标题进入侧栏。 */
function info(value: unknown): ConversationInfo {
  if (
    !record(value) ||
    typeof value.conversation_id !== 'string' ||
    !value.conversation_id.trim() ||
    typeof value.title !== 'string' ||
    typeof value.created_at !== 'string' ||
    !Number.isFinite(Date.parse(value.created_at)) ||
    typeof value.last_message_at !== 'string' ||
    !Number.isFinite(Date.parse(value.last_message_at))
  )
    throw new ApiError('会话目录格式无效')
  return {
    conversation_id: value.conversation_id,
    title: value.title,
    created_at: value.created_at,
    last_message_at: value.last_message_at,
  }
}
/** 校验分页外壳，拒绝无法继续读取的空游标。 */
function page(value: unknown): { items: unknown[]; next_cursor: string | null } {
  if (
    !record(value) ||
    !Array.isArray(value.items) ||
    !(
      value.next_cursor === null ||
      (typeof value.next_cursor === 'string' && value.next_cursor.trim())
    )
  )
    throw new ApiError('会话分页格式无效')
  return { items: value.items, next_cursor: value.next_cursor as string | null }
}
/** 使用统一认证接口读取 JSON，保留取消信号供账号退出释放资源。 */
async function request(path: string, signal: AbortSignal, method = 'GET'): Promise<unknown> {
  return readEnvelope(
    await authenticatedFetch(path, { method, headers: { Accept: 'application/json' }, signal }),
  )
}
/** 构造读取最近或更早记录的 URL；游标通过 URLSearchParams 编码，固定每批 20 条。 */
function url(path: string, cursor?: string | null): string {
  const query = new URLSearchParams({ limit: '20' })
  if (cursor) query.set('cursor', cursor)
  return `${path}?${query}`
}
/** 读取当前账号的会话目录，首次省略游标，后续传回服务端 next_cursor。 */
export async function listConversations(signal: AbortSignal, cursor?: string | null) {
  const data = page(await request(url('/api/conversations', cursor), signal))
  return { items: data.items.map(info), nextCursor: data.next_cursor }
}
/** 读取指定会话的公开历史，逐事件校验归属与类型；每批轮次必须按 seq 递增。 */
export async function conversationHistory(id: string, signal: AbortSignal, cursor?: string | null) {
  const raw = await request(url(`/api/conversations/${encodeURIComponent(id)}`, cursor), signal)
  const data = page(raw)
  if (!record(raw)) throw new ApiError('会话历史格式无效')
  const conversation = info(raw.conversation)
  if (conversation.conversation_id !== id) throw new ApiError('会话历史归属无效')
  let previous = 0
  // 把公开过程映射到现有时间线协议，同时拒绝混入其他会话或内部推理事件。
  const items = data.items.map((value): HistoryTurn => {
    if (
      !record(value) ||
      typeof value.turn_id !== 'string' ||
      !value.turn_id.trim() ||
      typeof value.seq !== 'number' ||
      !Number.isSafeInteger(value.seq) ||
      value.seq <= previous ||
      typeof value.user_content !== 'string' ||
      !(value.assistant_content === null || typeof value.assistant_content === 'string') ||
      !(value.assistant_message_id === null || typeof value.assistant_message_id === 'string') ||
      !['running', 'completed', 'failed', 'interrupted'].includes(String(value.status)) ||
      !Array.isArray(value.public_events)
    )
      throw new ApiError('会话轮次格式无效')
    previous = value.seq
    if (value.status === 'completed' && (!value.assistant_content || !value.assistant_message_id))
      throw new ApiError('完整历史缺少最终回复')
    // 历史只包含公开过程，不接受 start/done 或任意模型内部事件。
    const events = value.public_events.map((event) => {
      if (
        !record(event) ||
        !record(event.data) ||
        event.data.conversation_id !== id ||
        typeof event.event !== 'string' ||
        !['delta', 'tool_call', 'tool_start', 'tool_end', 'tool_error'].includes(event.event)
      )
        throw new ApiError('历史过程事件无效')
      return decodeEvent(event.event, event.data)
    })
    return {
      turn_id: value.turn_id,
      seq: value.seq,
      user_content: value.user_content,
      assistant_content: value.assistant_content,
      assistant_message_id: value.assistant_message_id,
      status: value.status as HistoryTurn['status'],
      events,
    }
  })
  return { conversation, items, nextCursor: data.next_cursor }
}
/** 软删除自己的会话；只在成功响应后从前端目录移除。 */
export async function deleteConversation(id: string, signal: AbortSignal): Promise<void> {
  const data = await request(`/api/conversations/${encodeURIComponent(id)}`, signal, 'DELETE')
  if (data !== null) throw new ApiError('删除会话响应格式无效')
}
