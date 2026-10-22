/** 聊天状态：管理当前页面的临时会话与流式请求，不持久化或恢复会话标识和正文。 */
import { computed, ref, type Ref } from 'vue'
import { defineStore } from 'pinia'
import { streamChatMessage } from '@/api/chat'
import type { ChatMessage, Conversation } from '@/types/chat'
import { finishActivities, updateActivity } from '@/utils/chatActivity'

/** 生成随机会话标识；普通 HTTP 环境没有 randomUUID 时使用浏览器随机字节。 */
function createThreadId(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) =>
    byte.toString(16).padStart(2, '0'),
  ).join('')
}

/** 创建聊天 store，供页面管理本次浏览中的会话与流式请求；首次加载预留随机 thread_id。 */
export const useChatStore = defineStore('chat', () => {
  // 明确 Ref 的公共类型，避免工具 JSON 的递归结构被类型系统反复做深层 UnwrapRef。
  const conversations: Ref<Conversation[]> = ref([])
  const activeId = ref<string | null>(null)
  const newThreadId = ref(createThreadId())
  // 当前会话可能不存在；空值统一表示首页，避免展示其他会话的残留消息。
  const activeConversation = computed(() =>
    conversations.value.find((item) => item.id === activeId.value),
  )
  // 判断当前会话是否还有未结束的请求，供输入区阻止同会话重复发送。
  const isSending = computed(
    () =>
      activeConversation.value?.messages.some(
        (message) => message.status === 'pending' || message.status === 'streaming',
      ) ?? false,
  )
  let sequence = 0

  /** 返回当前 store 内唯一的消息展示标识，与后端 thread_id 无关。 */
  function nextMessageId(): string {
    sequence += 1
    return `message-${sequence}`
  }

  /** 返回首页并预留新的会话标识；待用户发送后才把会话加入侧栏。 */
  function startNew(): void {
    newThreadId.value = createThreadId()
    activeId.value = null
  }

  /** 清空本页临时聊天展示，供退出或切换账号时隔离界面数据；不调用后端会话接口。 */
  function clearLocal(): void {
    conversations.value = []
    activeId.value = null
    newThreadId.value = createThreadId()
  }

  /** 选择本页已存在的会话并继续使用其 thread_id；未知标识不改变状态。 */
  function select(id: string): void {
    if (conversations.value.some((item) => item.id === id)) activeId.value = id
  }

  /**
   * 发送用户输入，并把流式回复和过程事件更新到所属会话。
   * text 去除首尾空白后写入用户消息，并创建助手占位；空白或同会话重复发送返回 false。
   * 每个会话仅允许一个在途请求；捕获原会话引用，切换页面内会话不会串写回复。
   * 失败保留用户消息及已收到的文本并标记未完成，返回 false；不自动重试。
   */
  async function send(text: string): Promise<boolean> {
    const content = text.trim()
    if (!content || isSending.value) return false
    if (!activeConversation.value) {
      const id = newThreadId.value
      conversations.value.unshift({
        id,
        title: Array.from(content).slice(0, 24).join(''),
        group: '今天',
        messages: [],
      })
      activeId.value = id
    }
    const conversation = activeConversation.value!
    const user: ChatMessage = {
      id: nextMessageId(),
      role: 'user',
      blocks: [{ type: 'paragraph', text: content }],
    }
    conversation.messages.push(user, {
      id: nextMessageId(),
      role: 'assistant',
      status: 'pending',
      blocks: [],
    })
    // 从响应式数组取得占位，保证异步更新能够触发组件重新渲染。
    const assistant = conversation.messages[conversation.messages.length - 1]!
    // blocks 保留临时正文便于失败诊断；可见顺序由 activities 维护，done 只替换最终正文。
    const segments = new Map<string, string>()
    try {
      for await (const event of streamChatMessage(content, conversation.id)) {
        updateActivity(assistant, event)
        if (event.type !== 'start') assistant.status = 'streaming'
        if (event.type === 'delta') {
          segments.set(event.messageId, (segments.get(event.messageId) ?? '') + event.text)
          // 将每段已累积正文映射为消息块，保留不同模型步骤的文本边界。
          assistant.blocks = Array.from(segments.values(), (text) => ({ type: 'paragraph', text }))
          assistant.status = 'streaming'
        } else if (event.type === 'done') {
          assistant.blocks = [{ type: 'paragraph', text: event.reply }]
          assistant.status = 'complete'
          finishActivities(assistant, true)
        }
      }
      return true
    } catch {
      finishActivities(assistant, false)
      assistant.status = 'error'
      return false
    }
  }

  return {
    conversations,
    activeId,
    activeConversation,
    isSending,
    startNew,
    select,
    send,
    clearLocal,
  }
})
