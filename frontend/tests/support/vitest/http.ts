/** 通用 HTTP 测试替身：提供统一响应与可控请求时序，业务身份和轮次数据留在各模块。 */

/** 每次创建可单独读取的响应体，用于模拟后端的统一响应与 HTTP/业务失败。 */
export function response(data: unknown, status = 200, code = 0, message = '成功'): Response {
  return new Response(JSON.stringify({ code, message, data }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** 创建可显式完成的请求，验证退出、页面切换与迟到响应的竞争边界。 */
export function deferredResponse() {
  let resolve!: (value: Response) => void
  // 由测试决定请求结束时间，不依赖真实网络时序。
  const promise = new Promise<Response>((done) => {
    resolve = done
  })
  return { promise, resolve }
}
