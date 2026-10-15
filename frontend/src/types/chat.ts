/** 聊天原型的数据契约：描述安全渲染的消息块与内存会话，不代表后端接口。 */
export type MessageBlock =
  | { type: 'paragraph'; text: string }
  | { type: 'list'; items: string[] }
  | { type: 'code'; language: string; text: string }

/** 消息展示状态；等待和失败用于组件预览，不产生真实请求。 */
export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  blocks: MessageBlock[]
  status?: 'complete' | 'pending' | 'error'
  demo?: boolean
}

/** 会话仅保存在当前页面内存中，刷新后恢复初始样例。 */
export interface Conversation {
  id: string
  title: string
  group: string
  messages: ChatMessage[]
}
