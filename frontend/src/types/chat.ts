/** 聊天展示数据契约：描述安全渲染的消息块和内存会话，API 数据由适配层转换。 */
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
}

/** 会话仅保存在当前页面内存中；id 同时作为后端 thread_id，刷新后不恢复。 */
export interface Conversation {
  id: string
  title: string
  group: string
  messages: ChatMessage[]
}
