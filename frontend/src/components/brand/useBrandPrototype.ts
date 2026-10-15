/** 品牌原型会话：独立的组件级状态，不读取正式 Pinia store、主题偏好或 localStorage。 */
import { computed, nextTick, ref } from 'vue'
import { createDemoConversations } from '@/data/demo'
import type { Conversation } from '@/types/chat'
import type { BrandPage } from './designs'

/** 创建本轮预览专属会话；切换视觉方案只换外观，保留同一份内容便于公平比较。 */
export function useBrandPrototype() {
  const conversations = ref<Conversation[]>(createDemoConversations())
  const activeId = ref<string | null>(null)
  const page = ref<BrandPage>('home')
  const draft = ref('')
  const scrollArea = ref<HTMLElement>()
  let sequence = 0
  // 选中标识只在本地会话列表中查找，缺失时回到首页。
  const activeConversation = computed(() =>
    conversations.value.find((item) => item.id === activeId.value),
  )

  /** DOM 更新后滚动当前原型消息容器，不影响外层设计说明的阅读位置。 */
  async function scrollToEnd(): Promise<void> {
    await nextTick()
    if (scrollArea.value) scrollArea.value.scrollTop = scrollArea.value.scrollHeight
  }

  /** 开启空白首页；首次发送时才创建新会话。 */
  function startNew(): void {
    activeId.value = null
    page.value = 'home'
    draft.value = ''
  }

  /** 选中指定演示会话并清除跨会话草稿，未知标识不产生变化。 */
  function selectConversation(id: string): void {
    if (!conversations.value.some((item) => item.id === id)) return
    activeId.value = id
    page.value = 'chat'
    draft.value = ''
    scrollToEnd()
  }

  /** 控制工具栏首页/对话页切换；没有活动会话时选取第一条样例。 */
  function setPage(value: BrandPage): void {
    if (value === 'home') {
      page.value = 'home'
      draft.value = ''
    } else {
      const id = activeConversation.value?.id ?? conversations.value[0]?.id
      if (id) selectConversation(id)
    }
  }

  /** 添加本地用户消息和明确标识的固定演示回复，返回是否实际发送。 */
  function send(text: string): boolean {
    const content = text.trim()
    if (!content) return false
    if (page.value === 'home' || !activeConversation.value) {
      sequence += 1
      const id = `brand-session-${sequence}`
      conversations.value.unshift({
        id,
        title: Array.from(content).slice(0, 20).join(''),
        group: '今天',
        messages: [],
      })
      activeId.value = id
    }
    sequence += 1
    activeConversation.value!.messages.push(
      {
        id: `brand-user-${sequence}`,
        role: 'user',
        blocks: [{ type: 'paragraph', text: content }],
      },
      {
        id: `brand-reply-${sequence}`,
        role: 'assistant',
        demo: true,
        blocks: [
          {
            type: 'paragraph',
            text: '这是品牌原型的固定演示回复，不由 AI 生成，也没有发送任何网络请求。',
          },
          {
            type: 'paragraph',
            text: '一个好想法，往往从一个清楚的问题开始。你可以沿着三个方向继续梳理：',
          },
          {
            type: 'list',
            items: [
              '确定希望抵达的结果。',
              '找到当下可以借力的信息与资源。',
              '先迈出一小步，再根据反馈调整航向。',
            ],
          },
        ],
      },
    )
    page.value = 'chat'
    draft.value = ''
    scrollToEnd()
    return true
  }

  return {
    conversations,
    activeId,
    activeConversation,
    page,
    draft,
    scrollArea,
    startNew,
    selectConversation,
    setPage,
    send,
  }
}
