/** 聊天展示数据契约：描述安全渲染的消息块和内存会话，API 数据由适配层转换。 */
import type { JsonValue, ToolKind } from './chat-events'
import type { ModelSelection, SelectionIssue } from '@/features/model-selection/types'

/** 过程状态；interrupted 表示没有收到完成确认，不等同于工具执行失败。 */
export type ActivityStatus = 'queued' | 'running' | 'complete' | 'error' | 'interrupted'

/** 助手公开正文，按 message_id 累积；done 到达后将最终正文移出过程时间线。 */
export interface TextActivity {
  type: 'text'
  id: string
  messageId: string
  text: string
  status: 'running' | 'complete' | 'interrupted'
}

/** 同一工具请求的一次实际执行；runId 区分重试或多次执行，结果允许为 null。 */
export interface ToolRun {
  runId: string
  kind: ToolKind
  status: Exclude<ActivityStatus, 'queued'>
  arguments?: { [key: string]: JsonValue } | string
  output?: JsonValue
  error?: string
}

/** 一次完整调用请求及其执行记录；未收到 start 时仅展示为已请求，不宣称正在执行。 */
export interface ToolActivity {
  type: 'tool'
  id: string
  toolCallId: string
  name: string
  kind?: ToolKind
  arguments?: { [key: string]: JsonValue }
  status: ActivityStatus
  error?: string
  runs: ToolRun[]
}

/** 按首次到达顺序交错展示正文和工具请求，执行更新原条目，不按名称重新排序。 */
export type ChatActivity = TextActivity | ToolActivity
export type MessageBlock =
  | { type: 'paragraph'; text: string }
  | { type: 'list'; items: string[] }
  | { type: 'code'; language: string; text: string }

/** 消息展示状态；等待首段、接收增量、确认完成与失败均由流式请求驱动。 */
export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  blocks: MessageBlock[]
  status?: 'complete' | 'pending' | 'streaming' | 'error'
  demo?: boolean
  activities?: ChatActivity[]
  /** 请求或历史状态的安全说明，不包含底层异常或认证凭据。 */
  error?: string
}

/** 会话展示缓存；persisted 时 id 为服务端 ID，否则仅是尚未收到 start 的本地展示键。 */
export interface Conversation {
  modelSelection?: ModelSelection | null
  modelSelectionVersion?: number
  modelSelectionIssue?: SelectionIssue | null
  selectionSaving?: boolean
  selectionError?: string
  selectionRead?: number
  rejectedDraft?: string
  id: string
  title: string
  group: string
  messages: ChatMessage[]
  persisted?: boolean
  createdAt?: string
  lastMessageAt?: string
  loaded?: boolean
  nextCursor?: string | null
  loading?: boolean
  historyError?: string
  running?: boolean
  remoteRunning?: boolean
  deleting?: boolean
  unavailable?: boolean
  /** 本地消息的变更序号，防止较早发出的目录刷新覆盖刚创建或更新的会话。 */
  localRevision?: number
}
