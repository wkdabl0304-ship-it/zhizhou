/** 聊天 SSE 适配：通过 POST fetch 逐事件读取响应，校验会话、事件顺序及终止状态。 */

import type { ChatStreamEvent, JsonValue, ToolKind } from '@/types/chat-events'
export type { ChatStreamEvent } from '@/types/chat-events'

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
function decodeEvent(
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

/** SSE 传输帧；data 保留原始文本，业务层再执行 JSON 及字段校验。 */
interface EventFrame {
  event: string
  data: string
}

/**
 * 从 HTTP 响应体逐个读取完整的 SSE 传输帧。
 * body 提供原始字节流；增量解码 UTF-8，再按 SSE 空行分帧，yield 事件名和原始 data。
 * 兼容跨网络块的字符、CRLF、CR 和多行 data，业务字段留给调用方校验。
 * 退出迭代或解析失败时取消读取并释放锁；未以空行结束的帧不作为完整事件交付。
 */
async function* readEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<EventFrame> {
  const reader = body.getReader()
  const decoder = new TextDecoder('utf-8', { fatal: true })
  let buffer = ''
  let event = ''
  let data: string[] = []

  /** 解析一行 SSE 文本并组装当前帧；空行返回完整帧，其他行更新缓冲或被忽略。 */
  function consumeLine(line: string): EventFrame | undefined {
    if (line === '') {
      const frame = data.length ? { event, data: data.join('\n') } : undefined
      event = ''
      data = []
      return frame
    }
    const colon = line.indexOf(':')
    const field = colon < 0 ? line : line.slice(0, colon)
    const value = colon < 0 ? '' : line.slice(colon + 1).replace(/^ /, '')
    if (field === 'event') event = value
    if (field === 'data') data.push(value)
  }

  try {
    let ended = false
    while (!ended) {
      const chunk = await reader.read()
      ended = chunk.done
      buffer += ended ? decoder.decode() : decoder.decode(chunk.value, { stream: true })
      while (true) {
        const index = buffer.search(/[\r\n]/)
        if (index < 0) break
        // CRLF 的两个字节可能分属网络块；保留末尾 CR，避免误判为空行。
        if (!ended && buffer[index] === '\r' && index === buffer.length - 1) break
        const width = buffer[index] === '\r' && buffer[index + 1] === '\n' ? 2 : 1
        const frame = consumeLine(buffer.slice(0, index))
        buffer = buffer.slice(index + width)
        if (frame) yield frame
      }
    }
  } finally {
    // 即使已收到终止事件，服务端也可能尚未关闭连接；主动取消，避免保留在途读取。
    try {
      await reader.cancel()
    } catch {
      // 网络断开时取消也可能失败，不覆盖最初的解析或传输异常。
    }
    reader.releaseLock()
  }
}

/**
 * 向后端发送一轮聊天，并向 store 逐个提供可用于更新界面的业务事件。
 * message 为正文，threadId 为当前前端协议的会话标识；依次 yield 已校验事件，
 * 收到 done 后结束，不等待网络连接关闭。
 * HTTP/流内错误、格式错误、会话不匹配或缺少终止事件均抛出异常；不自动重试请求。
 * 同源 /api 路径开发时由 Vite 代理，部署时由反向代理转发且需关闭流缓冲。
 */
export async function* streamChatMessage(
  message: string,
  threadId: string,
): AsyncGenerator<ChatStreamEvent> {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ message, thread_id: threadId }),
  })
  if (!response.ok) throw new Error('聊天请求失败')
  if (
    response.headers.get('content-type')?.split(';')[0]?.trim() !== 'text/event-stream' ||
    !response.body
  ) {
    await response.body?.cancel()
    throw new Error('聊天响应不是 SSE')
  }

  let started = false
  for await (const frame of readEvents(response.body)) {
    const payload: unknown = JSON.parse(frame.data)
    if (!payload || typeof payload !== 'object' || !('code' in payload))
      throw new Error('聊天事件格式无效')
    if (frame.event === 'error' || payload.code !== 0) throw new Error('聊天生成失败')
    const data = 'data' in payload ? payload.data : null
    if (
      !data ||
      typeof data !== 'object' ||
      Array.isArray(data) ||
      !('thread_id' in data) ||
      data.thread_id !== threadId
    )
      throw new Error('聊天事件会话标识无效')

    if (frame.event === 'start') {
      if (started) throw new Error('聊天开始事件重复')
      started = true
      yield { type: 'start', threadId }
      continue
    }
    if (!started) throw new Error('缺少聊天开始事件')
    const event = decodeEvent(frame.event, data)
    yield event
    if (event.type === 'done') return
  }
  throw new Error('聊天流在确认完成前中断')
}
