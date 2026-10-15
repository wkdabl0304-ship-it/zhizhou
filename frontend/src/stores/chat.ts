/** 聊天原型状态：隔离演示会话与视图，整个模块不发起网络请求、不持久化聊天正文。 */
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { createDemoConversations } from '@/data/demo'
import type { ChatMessage } from '@/types/chat'

export const useChatStore = defineStore('chat', () => {
  const conversations = ref(createDemoConversations())
  const activeId = ref<string | null>(null)
  // 当前会话可能不存在；空值统一表示首页，避免展示其他会话的残留消息。
  const activeConversation = computed(() =>
    conversations.value.find((item) => item.id === activeId.value),
  )
  let sequence = 0

  /** 返回新的内存标识；同一 store 生命周期内不重复，不作为后端会话标识。 */
  function nextId(prefix: string): string {
    sequence += 1
    return `${prefix}-${sequence}`
  }

  /** 返回首页；待用户实际发送时才创建会话，避免空会话堆积。 */
  function startNew(): void {
    activeId.value = null
  }

  /** 选择已存在的演示会话；未知标识不改变当前状态。 */
  function select(id: string): void {
    if (conversations.value.some((item) => item.id === id)) activeId.value = id
  }

  /** 添加用户消息与固定演示回复；返回是否发送成功，空白输入不改变任何会话。 */
  function send(text: string): boolean {
    const content = text.trim()
    if (!content) return false
    if (!activeConversation.value) {
      const id = nextId('conversation')
      conversations.value.unshift({
        id,
        title: Array.from(content).slice(0, 24).join(''),
        group: '今天',
        messages: [],
      })
      activeId.value = id
    }
    const messages = activeConversation.value!.messages
    const user: ChatMessage = {
      id: nextId('message'),
      role: 'user',
      blocks: [{ type: 'paragraph', text: content }],
    }
    messages.push(user, {
      id: nextId('message'),
      role: 'assistant',
      demo: true,
      blocks: [
        {
          type: 'paragraph',
          text: '这是用于体验界面的固定演示回复，尚未连接 AI 服务。你的内容仅保存在当前页面中。',
        },
        { type: 'paragraph', text: '处理一项工作时，可以先用这三个问题梳理思路：' },
        {
          type: 'list',
          items: [
            '希望获得什么具体结果？',
            '目前有哪些已知信息和限制？',
            '可以先完成的最小一步是什么？',
          ],
        },
        { type: 'paragraph', text: '你可以继续输入，或从左侧打开其他示例对话，体验消息排版。' },
      ],
    })
    return true
  }

  return { conversations, activeId, activeConversation, startNew, select, send }
})
