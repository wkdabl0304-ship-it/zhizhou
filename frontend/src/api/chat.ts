/** 聊天 API 适配：调用非流式后端接口并校验统一响应，供聊天 store 使用。 */

/** 后端成功响应中的业务数据；thread_id 应与本轮请求保持一致。 */
interface ChatReply {
  reply: string
  thread_id: string
}

/**
 * 发送一轮消息；HTTP、业务失败及无效响应均抛出异常，由调用方更新失败状态。
 * 使用同源路径，开发时由 Vite 代理，部署时由反向代理转发 /api。
 */
export async function sendChatMessage(message: string, threadId: string): Promise<ChatReply> {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, thread_id: threadId }),
  })
  if (!response.ok) throw new Error('聊天请求失败')

  // 网络数据不能只依赖 TypeScript 断言；避免将业务错误或异常数据展示为成功回复。
  const body: unknown = await response.json()
  if (!body || typeof body !== 'object' || !('code' in body) || body.code !== 0)
    throw new Error('聊天业务处理失败')
  const data = 'data' in body ? body.data : null
  if (
    !data ||
    typeof data !== 'object' ||
    !('reply' in data) ||
    typeof data.reply !== 'string' ||
    !data.reply.trim() ||
    !('thread_id' in data) ||
    data.thread_id !== threadId
  )
    throw new Error('聊天响应格式无效')

  return { reply: data.reply, thread_id: threadId }
}
