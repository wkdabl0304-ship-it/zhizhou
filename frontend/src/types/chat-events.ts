/** 聊天流事件契约：描述 API 校验后交给状态层的事件，字段统一使用前端命名。 */

/** 后端公开的 JSON 值；工具参数与结果可为结构化数据，不包含可执行对象。 */
export type JsonValue =
  null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue }

/** 后端声明的工具展示类型；前端不根据工具名或参数猜测是否为命令。 */
export type ToolKind = 'tool' | 'command'

/** 事件在 API 层已完成类型与 thread_id 校验；顶层 error 由异常通道交付。 */
export type ChatStreamEvent =
  | { type: 'start'; threadId: string }
  | { type: 'delta'; messageId: string; text: string }
  | { type: 'done'; messageId: string; reply: string }
  | {
      type: 'tool_call'
      messageId: string
      toolCallId: string
      name: string
      arguments: { [key: string]: JsonValue }
    }
  | {
      type: 'tool_start'
      toolCallId: string
      runId: string
      name: string
      kind: ToolKind
      arguments: { [key: string]: JsonValue } | string
    }
  | {
      type: 'tool_end'
      toolCallId: string
      runId: string
      name: string
      kind: ToolKind
      output: JsonValue
    }
  | {
      type: 'tool_error'
      toolCallId: string
      runId: string | null
      name: string
      kind: ToolKind
      message: string
    }
