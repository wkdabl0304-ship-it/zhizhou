/** SSE 测试辅助：编码后端事件并构造可控字节流，不连接网络或模型。 */

/** 编码统一响应事件；JSON 保留真实换行转义，空行作为 SSE 帧边界。 */
export function eventFrame(event: string, data: unknown, code = 0): string {
  return `event: ${event}\ndata: ${JSON.stringify({ code, message: code ? '生成失败' : '成功', data })}\n\n`
}

/** 返回 SSE 类型响应；文本作为浏览器可逐字节读取的 UTF-8 响应体。 */
export function sseResponse(text: string): Response {
  return new Response(text, { headers: { 'Content-Type': 'text/event-stream; charset=utf-8' } })
}

/** 构造完整成功轮次，回显会话标识并提供 start、delta、done 三类事件。 */
export function success(threadId: string, reply = '后端真实格式的回复'): Response {
  const message_id = 'reply-1'
  return sseResponse(
    eventFrame('start', { thread_id: threadId }) +
      eventFrame('delta', { thread_id: threadId, message_id, text: reply }) +
      eventFrame('done', { thread_id: threadId, message_id, reply }),
  )
}

/**
 * 创建由测试主动推进的流，模拟首段提前到达、生成等待和断开；终止测试时须 close/fail。
 * cancel 由消费方执行，用于确认 done/error 后即释放读取，不依赖服务端主动关连接。
 */
export function controlledStream() {
  let controller!: ReadableStreamDefaultController<Uint8Array>
  let cancelled = false
  const body = new ReadableStream<Uint8Array>({
    // 捕获生产端，使测试可在断言中间状态后继续推送事件。
    start(value) {
      controller = value
    },
    // 记录消费方清理，避免终止后测试继续向已关闭的控制器写入。
    cancel() {
      cancelled = true
    },
  })
  return {
    response: new Response(body, { headers: { 'Content-Type': 'text/event-stream' } }),
    /** 推送文本或任意字节块，允许测试把 UTF-8 字符和事件拆到多个网络块。 */
    push(value: string | Uint8Array): void {
      controller.enqueue(typeof value === 'string' ? new TextEncoder().encode(value) : value)
    },
    /** 模拟服务端正常关闭；若客户端已经取消则无需再次操作控制器。 */
    close(): void {
      if (!cancelled) controller.close()
    },
    /** 模拟连接在接收途中失败，消费者应保留部分文本并退出等待。 */
    fail(): void {
      controller.error(new TypeError('connection lost'))
    },
    /** 返回消费方是否已清理此响应体，不访问实现内部的 reader。 */
    isCancelled(): boolean {
      return cancelled
    },
  }
}
