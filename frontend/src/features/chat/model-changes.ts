/** 模型变化依据：仅将已产生回复的实际轮次作为发送确认与分界线的比较基准。 */
import type { ModelIdentity } from '@/features/model-selection/types'
import type { ChatMessage } from './types'

/** 取得最近一次已开始回复的模型，未输出轮次跳过，旧历史身份缺失时不推测。 */
export function lastReplyModel(messages: ChatMessage[]): ModelIdentity | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]!
    if (message.role !== 'user' || message.modelReplyStarted === false) continue
    return message.model ?? null
  }
  return null
}
