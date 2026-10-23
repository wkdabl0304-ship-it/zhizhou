/** SSE 测试辅助：编码后端事件并构造可控字节流，不连接网络或模型。 */

/** 将任意数据编码为一帧 SSE，不注入业务字段或响应信封。 */
export function eventFrame(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
}

/** 将事件文本包装成测试用 SSE 响应；正文由浏览器响应流按 UTF-8 编码读取。 */
export function sseResponse(text: string): Response {
  return new Response(text, { headers: { 'Content-Type': 'text/event-stream; charset=utf-8' } })
}

/**
 * 创建测试可手动推进的 SSE 响应，用于断言生成过程中的中间状态。
 * 返回响应和 push/close/fail 等控制方法，模拟首段提前到达、生成等待和断开；
 * 终止测试时须 close/fail，避免留下未完成的生产流。
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
