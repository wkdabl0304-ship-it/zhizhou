/** 聊天场景适配：组合纯数据与通用 SSE 替身，不将业务默认值放入传输工具。 */
import { chatEventData, completedChatEvents } from '../data/chat'
import { eventFrame as encodeFrame, sseResponse } from './sse'
import { modelOptionsData } from '../data/model-selection'
import { response } from './http'

/** 为只测聊天/目录的组件提供独立选项响应，不消耗其聊天或目录一次性替身。 */
export function withModelOptions(fetcher: typeof fetch): typeof fetch {
  return async (input, init) =>
    String(input).endsWith('/api/model-config/options')
      ? response(modelOptionsData())
      : fetcher(input, init)
}

/** 将聊天契约数据包装为统一响应信封，再交给通用 SSE 编码器。 */
export function eventFrame(event: string, data: unknown, code = 0): string {
  return encodeFrame(event, {
    code,
    message: code ? '生成失败' : '成功',
    data: chatEventData(event, data),
  })
}

/** 创建一个独立的成功聊天响应，调用方可控制会话、正文和首轮标记。 */
export function success(
  conversationId: string,
  reply = '后端真实格式的回复',
  isNew = true,
): Response {
  return sseResponse(
    completedChatEvents(conversationId, reply, isNew)
      .map(([event, data]) => eventFrame(event, data))
      .join(''),
  )
}
