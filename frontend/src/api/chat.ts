/** 聊天 SSE 适配：通过 POST fetch 逐事件读取响应，校验会话、事件顺序及终止状态。 */

/** 已校验的成功事件；error 事件转为异常，调用方不需要自行检查业务码。 */
export type ChatStreamEvent =
  | { type: 'start'; threadId: string }
  | { type: 'delta'; messageId: string; text: string }
  | { type: 'done'; messageId: string; reply: string }

/** SSE 传输帧；data 保留原始文本，业务层再执行 JSON 及字段校验。 */
interface EventFrame {
  event: string
  data: string
}

/**
 * 增量解码 UTF-8 并按 SSE 空行分帧，兼容跨网络块的字符、CRLF、CR 和多行 data。
 * 退出迭代或解析失败时取消读取并释放锁；未以空行结束的帧不作为完整事件交付。
 */
async function* readEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<EventFrame> {
  const reader = body.getReader()
  const decoder = new TextDecoder('utf-8', { fatal: true })
  let buffer = ''
  let event = ''
  let data: string[] = []

  /** 接收一行协议字段；空行提交事件，注释、id 和 retry 不参与本接口的业务数据。 */
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
 * 发送一轮消息，依次 yield 已校验事件；收到 done 后结束，不等待网络连接关闭。
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
    if (!data || typeof data !== 'object' || !('thread_id' in data) || data.thread_id !== threadId)
      throw new Error('聊天事件会话标识无效')

    if (frame.event === 'start') {
      if (started) throw new Error('聊天开始事件重复')
      started = true
      yield { type: 'start', threadId }
      continue
    }
    if (!started) throw new Error('缺少聊天开始事件')
    if (!('message_id' in data) || typeof data.message_id !== 'string' || !data.message_id.trim())
      throw new Error('聊天消息标识无效')
    if (frame.event === 'delta' && 'text' in data && typeof data.text === 'string') {
      yield { type: 'delta', messageId: data.message_id, text: data.text }
    } else if (
      frame.event === 'done' &&
      'reply' in data &&
      typeof data.reply === 'string' &&
      data.reply.trim()
    ) {
      yield { type: 'done', messageId: data.message_id, reply: data.reply }
      return
    } else {
      throw new Error('聊天事件类型或数据无效')
    }
  }
  throw new Error('聊天流在确认完成前中断')
}
