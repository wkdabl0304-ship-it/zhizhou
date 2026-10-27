/** 历史展示适配：复用流式时间线归并，恢复最终回答、公开工具与未完成状态。 */
import type { ChatMessage } from '@/features/chat/types'
import { finishActivities, updateActivity } from '@/features/chat/activity'
import type { HistoryTurn } from './api/conversations'

/** 将一轮业务历史转为稳定标识的两条消息，分页去重不会依赖消息正文是否相同。 */
export function turnMessages(turn: HistoryTurn): ChatMessage[] {
  const completed = turn.status === 'completed'
  const assistant: ChatMessage = {
    id: `${turn.turn_id}-assistant`,
    role: 'assistant',
    blocks: [],
    status: completed ? 'complete' : 'error',
  }
  for (const event of turn.events) updateActivity(assistant, event)
  if (completed) {
    assistant.blocks = [{ type: 'paragraph', text: turn.assistant_content! }]
    updateActivity(assistant, {
      type: 'done',
      messageId: turn.assistant_message_id!,
      reply: turn.assistant_content!,
    })
  } else {
    // 部分正文保留在时间线，不作为最终回答，也不把旧 running 记录显示成当前连接的流。
    assistant.error =
      turn.status === 'running'
        ? '此轮仍在生成，完成后将自动同步。'
        : turn.status === 'interrupted'
          ? '此轮已中断，已保存的内容仍然保留。'
          : '此轮未完成，已保存的内容仍然保留。'
  }
  finishActivities(assistant, completed)
  return [
    {
      id: `${turn.turn_id}-user`,
      role: 'user',
      blocks: [{ type: 'paragraph', text: turn.user_content }],
    },
    assistant,
  ]
}
