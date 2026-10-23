/** 聊天公开事件适配：校验正文和工具字段，供实时 SSE 与持久化历史共同使用。 */
import type { ChatStreamEvent, JsonValue, ToolKind } from '../chat-events'

/** 判断网络数据是否只包含协议允许的 JSON 值；递归校验对象与数组，并拒绝非有限数值。 */
function isJsonValue(value: unknown): value is JsonValue {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return true
  if (typeof value === 'number') return Number.isFinite(value)
  if (Array.isArray(value)) return value.every(isJsonValue)
  return typeof value === 'object' && Object.values(value).every(isJsonValue)
}

/** 读取协议中的非空标识或名称，避免错误数据进入过程关联逻辑。 */
function requiredString(data: Record<string, unknown>, key: string): string {
  const value = data[key]
  if (typeof value !== 'string' || !value.trim()) throw new Error(`聊天事件 ${key} 无效`)
  return value
}

/** 读取并校验工具的展示类型；只接受后端声明的 tool/command，非法值抛出异常。 */
function toolKind(data: Record<string, unknown>): ToolKind {
  if (data.kind !== 'tool' && data.kind !== 'command') throw new Error('聊天工具类型无效')
  return data.kind
}

/**
 * 将后端业务事件转换为前端聊天状态使用的类型化事件。
 * type 指定事件种类，data 提供已解析的字段；校验失败时抛出异常。
 * start 由调用方单独处理，工具执行事件只读取实际存在的调用和运行标识。
 */
export function decodeEvent(
  type: string,
  data: Record<string, unknown>,
): Exclude<ChatStreamEvent, { type: 'start' }> {
  if (type === 'delta') {
    if (typeof data.text !== 'string') throw new Error('聊天文本增量无效')
    return { type, messageId: requiredString(data, 'message_id'), text: data.text }
  }
  if (type === 'done')
    return {
      type,
      messageId: requiredString(data, 'message_id'),
      reply: requiredString(data, 'reply'),
    }
  const toolCallId = requiredString(data, 'tool_call_id')
  const name = requiredString(data, 'name')
  if (type === 'tool_call') {
    if (
      !isJsonValue(data.arguments) ||
      !data.arguments ||
      typeof data.arguments !== 'object' ||
      Array.isArray(data.arguments)
    )
      throw new Error('聊天工具请求参数无效')
    return {
      type,
      messageId: requiredString(data, 'message_id'),
      toolCallId,
      name,
      arguments: data.arguments,
    }
  }
  const kind = toolKind(data)
  if (type === 'tool_start') {
    if (
      !isJsonValue(data.arguments) ||
      data.arguments === null ||
      (typeof data.arguments !== 'string' &&
        (typeof data.arguments !== 'object' || Array.isArray(data.arguments)))
    )
      throw new Error('聊天工具执行参数无效')
    return {
      type,
      toolCallId,
      name,
      kind,
      runId: requiredString(data, 'run_id'),
      arguments: data.arguments,
    }
  }
  if (type === 'tool_end' && isJsonValue(data.output))
    return {
      type,
      toolCallId,
      name,
      kind,
      runId: requiredString(data, 'run_id'),
      output: data.output,
    }
  if (type === 'tool_error') {
    const runId = data.run_id === null ? null : requiredString(data, 'run_id')
    return { type, toolCallId, name, kind, runId, message: requiredString(data, 'message') }
  }
  throw new Error('聊天事件类型或数据无效')
}
