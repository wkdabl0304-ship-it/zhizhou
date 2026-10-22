/** 聊天时间线归并：保留公开正文与工具的到达顺序，完成时分离最终回答。 */
import type { ChatMessage, ToolActivity } from '@/types/chat'
import type { ChatStreamEvent } from '@/types/chat-events'

/** 结束消息时间线中仍在输出的正文阶段；interrupted 决定标记为中断还是完成。 */
function closeText(message: ChatMessage, interrupted = false): void {
  for (const item of message.activities ?? []) {
    if (item.type === 'text' && item.status === 'running')
      item.status = interrupted ? 'interrupted' : 'complete'
  }
}

/** 汇总工具卡片的显示状态；任一执行仍在运行时保持执行中，否则采用最后一次执行的状态。 */
function updateToolStatus(tool: ToolActivity): void {
  tool.status = tool.runs.some((run) => run.status === 'running')
    ? 'running'
    : tool.runs[tool.runs.length - 1]!.status
}

/**
 * 将一个聊天事件合并到助手消息的过程时间线中，供界面按到达顺序展示。
 * 原地修改 message.activities：正文按消息标识累积，工具按调用与执行标识更新；
 * done 仅移出最终回答对应的过程正文，让最终回答在独立正文区展示。
 * 无 tool_call 的执行事件也创建卡片；run_id 为 null 的拒绝保留为请求失败，不伪造执行记录。
 */
export function updateActivity(message: ChatMessage, event: ChatStreamEvent): void {
  if (event.type === 'start') return
  message.activities ??= []
  // 从响应式消息重新读取数组，避免首次赋值表达式返回原始数组而漏掉增量通知。
  const activities = message.activities
  if (event.type === 'delta') {
    let text = activities.find((item) => item.type === 'text' && item.messageId === event.messageId)
    if (!text) {
      closeText(message)
      activities.push({
        type: 'text',
        id: `text-${event.messageId}`,
        messageId: event.messageId,
        text: '',
        status: 'running',
      })
      text = activities[activities.length - 1]!
    }
    if (text.type === 'text') {
      text.text += event.text
      text.status = 'running'
    }
    return
  }
  closeText(message)
  if (event.type === 'done') {
    // 最终回答已经有独立正文；按标识移除，不能用文本相等误删之前的进度说明。
    message.activities = activities.filter(
      (item) => item.type !== 'text' || item.messageId !== event.messageId,
    )
    return
  }
  let tool = activities.find(
    (item): item is ToolActivity => item.type === 'tool' && item.toolCallId === event.toolCallId,
  )
  if (!tool) {
    activities.push({
      type: 'tool',
      id: `tool-${event.toolCallId}`,
      toolCallId: event.toolCallId,
      name: event.name,
      status: 'queued',
      runs: [],
    })
    tool = activities[activities.length - 1] as ToolActivity
  }
  if (event.type === 'tool_call') {
    tool.arguments = event.arguments
    return
  }
  tool.kind = event.kind
  if (event.type === 'tool_error' && event.runId === null) {
    tool.error = event.message
    tool.status = tool.runs.some((run) => run.status === 'running') ? 'running' : 'error'
    return
  }
  let run = tool.runs.find((item) => item.runId === event.runId)
  if (!run) {
    tool.runs.push({ runId: event.runId!, kind: event.kind, status: 'running' })
    run = tool.runs[tool.runs.length - 1]!
  }
  if (event.type === 'tool_start') {
    run.arguments = event.arguments
  } else if (event.type === 'tool_end') {
    run.status = 'complete'
    run.output = event.output
  } else if (event.type === 'tool_error') {
    run.status = 'error'
    run.error = event.message
  }
  updateToolStatus(tool)
}

/**
 * 在本轮聊天结束时收尾过程卡片，避免界面继续显示执行中。
 * succeeded 决定正文是否算正常结束；未收到结果的工具标记为未确认完成，
 * 已确认的成功或失败结果保留，不根据传输是否中断推断工具结果。
 */
export function finishActivities(message: ChatMessage, succeeded: boolean): void {
  closeText(message, !succeeded)
  for (const tool of message.activities ?? []) {
    if (tool.type !== 'tool') continue
    for (const run of tool.runs) {
      if (run.status === 'running') run.status = 'interrupted'
    }
    if (tool.status === 'queued' || tool.status === 'running') tool.status = 'interrupted'
  }
}
