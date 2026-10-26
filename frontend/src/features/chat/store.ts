/** 聊天状态：管理服务端会话目录、游标历史和流式续聊；缓存随账号退出清除。 */
import { computed, onScopeDispose, ref, watch, type Ref } from 'vue'
import { defineStore } from 'pinia'
import { streamChatMessage } from '@/features/chat/api/stream'
import { ApiError } from '@/features/auth/authenticated'
import { useAuthStore } from '@/features/auth/store'
import {
  listConversations,
  conversationHistory,
  deleteConversation,
  type ConversationInfo,
} from '@/features/chat/api/conversations'
import { turnMessages } from '@/features/chat/history'
import type { ChatMessage, Conversation } from '@/features/chat/types'
import { finishActivities, updateActivity } from '@/features/chat/activity'

/** 将安全接口错误转换为页面说明；取消与未知异常不泄露底层细节。 */
function explain(error: unknown): string {
  return error instanceof ApiError ? error.message : '请求未完成，请稍后重试'
}
/** 按用户本地日期分组目录，使用日期边界而非固定 24 小时处理夏令时。 */
function group(at: string): string {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)
  const time = Date.parse(at)
  return time >= +today ? '今天' : time >= +yesterday ? '昨天' : '更早'
}
/** 创建聊天业务状态；公开入口保持集中，HTTP 和历史展示转换各自放在独立模块。 */
export const useChatStore = defineStore('chat', () => {
  const auth = useAuthStore()
  const conversations: Ref<Conversation[]> = ref([])
  const activeId = ref<string | null>(null)
  const listing = ref(false)
  const listError = ref('')
  const listInitialized = ref(false)
  const nextCursor = ref<string | null>(null)
  const actionError = ref('')
  const lastErrorCode = ref<number>()
  // 草稿只在内存中跨管理页保留，切换会话或退出时清空，不写入浏览器存储。
  const draft = ref('')
  const activeConversation = computed(() =>
    conversations.value.find((item) => item.id === activeId.value),
  )
  const isSending = computed(() => !!activeConversation.value?.running)
  watch(activeConversation, () => {
    draft.value = ''
  })
  const inputBlocked = computed(() => {
    const row = activeConversation.value
    return (
      !!row &&
      (!!row.loading ||
        !!row.deleting ||
        !!row.remoteRunning ||
        !!row.unavailable ||
        row.loaded === false)
    )
  })
  const controllers = new Set<AbortController>()
  const histories = new Map<Conversation, AbortController>()
  let epoch = 0
  let sequence = 0
  let mutation = 0

  /** 为一次业务操作分配取消控制器，退出账号或销毁 store 时统一释放。 */
  function controller(): AbortController {
    const value = new AbortController()
    controllers.add(value)
    return value
  }
  /** 判断响应仍属于当前账号和现存会话，阻止迟到结果复活已删除的数据。 */
  function current(version: number, row?: Conversation): boolean {
    return version === epoch && (!row || conversations.value.includes(row))
  }
  /** 按最近消息时间排序，相同时间使用服务端 ID 次键。 */
  function sort(): void {
    conversations.value.sort(
      (a, b) =>
        (Date.parse(b.lastMessageAt ?? '') || 0) - (Date.parse(a.lastMessageAt ?? '') || 0) ||
        b.id.localeCompare(a.id),
    )
  }
  /** 将服务端元数据写入展示缓存，不丢失已有正文、分页与请求状态。 */
  function metadata(row: Conversation, info: ConversationInfo): void {
    row.title = info.title
    row.createdAt = info.created_at
    row.lastMessageAt = info.last_message_at
    row.group = group(info.last_message_at)
    row.persisted = true
  }
  /** 创建尚未读取正文的服务端目录条目，只有选中后才请求历史。 */
  function entry(info: ConversationInfo): Conversation {
    return {
      id: info.conversation_id,
      title: info.title,
      group: group(info.last_message_at),
      messages: [],
      persisted: true,
      createdAt: info.created_at,
      lastMessageAt: info.last_message_at,
      loaded: false,
    }
  }
  /** 清空账号缓存并取消全部在途请求；这里只清理浏览器状态，不删除服务端会话。 */
  function clearLocal(): void {
    epoch += 1
    draft.value = ''
    lastErrorCode.value = undefined
    for (const pending of controllers) pending.abort()
    controllers.clear()
    histories.clear()
    conversations.value = []
    activeId.value = null
    listing.value = false
    nextCursor.value = null
    listError.value = ''
    actionError.value = ''
    listInitialized.value = false
  }
  // 账号隔离属于业务 store，不依赖某个页面是否仍挂载；退出会同时取消模型流和目录读取。
  watch(
    () => auth.user?.id,
    (identity, previous) => {
      if (previous && previous !== identity) clearLocal()
    },
    { flush: 'sync' },
  )
  onScopeDispose(clearLocal)

  /** 读取最近或更早会话，合并重叠页；刷新保留当前会话及请求后新增的数据。 */
  async function loadConversations(more = false): Promise<void> {
    if (listing.value || !auth.isAuthenticated || (more && !nextCursor.value)) return
    const version = epoch
    const stamp = mutation
    const request = controller()
    const cursor = more ? nextCursor.value : null
    listing.value = true
    listError.value = ''
    try {
      const page = await listConversations(request.signal, cursor)
      if (!current(version)) return
      if (cursor && page.nextCursor === cursor) throw new ApiError('会话游标未推进，请刷新目录')
      const existing = new Map(conversations.value.map((row) => [row.id, row]))
      const incoming = page.items.map((info) => {
        const row = existing.get(info.conversation_id) ?? entry(info)
        if ((row.localRevision ?? 0) <= stamp && !row.running) metadata(row, info)
        return row
      })
      const retained = more
        ? conversations.value
        : conversations.value.filter(
            (row) =>
              row.id === activeId.value ||
              row.running ||
              !row.persisted ||
              (row.localRevision ?? 0) > stamp,
          )
      conversations.value = [
        ...new Map([...retained, ...incoming].map((row) => [row.id, row])).values(),
      ]
      sort()
      nextCursor.value = page.nextCursor
      listInitialized.value = true
    } catch (error) {
      if (current(version)) listError.value = explain(error)
    } finally {
      controllers.delete(request)
      if (current(version)) listing.value = false
    }
  }
  /** 读取选中会话的最近历史或更早轮次；生成期间不允许历史响应覆盖正在接收的消息。 */
  async function loadHistory(row: Conversation, more = false): Promise<void> {
    if (!row.persisted || row.loading || row.running || row.deleting || (more && !row.nextCursor))
      return
    const version = epoch
    const request = controller()
    histories.set(row, request)
    const cursor = more ? row.nextCursor : null
    row.loading = true
    row.historyError = ''
    try {
      const page = await conversationHistory(row.id, request.signal, cursor)
      if (!current(version, row)) return
      if (cursor && page.nextCursor === cursor) throw new ApiError('历史游标未推进，请刷新会话')
      const older = page.items.flatMap(turnMessages)
      row.messages = more
        ? [...new Map([...older, ...row.messages].map((message) => [message.id, message])).values()]
        : older
      row.nextCursor = page.nextCursor
      row.loaded = true
      row.unavailable = false
      row.remoteRunning =
        (more && row.remoteRunning) || page.items.some((turn) => turn.status === 'running')
      metadata(row, page.conversation)
      sort()
    } catch (error) {
      if (current(version, row)) {
        row.historyError = explain(error)
        if (error instanceof ApiError && error.status === 404) row.unavailable = true
      }
    } finally {
      histories.delete(row)
      controllers.delete(request)
      if (current(version, row)) row.loading = false
    }
  }
  /** 选中目录条目，首次按需读取历史；已加载或正在生成的会话直接使用当前缓存。 */
  async function select(id: string): Promise<void> {
    const row = conversations.value.find((item) => item.id === id)
    if (!row) return
    activeId.value = id
    actionError.value = ''
    if (!row.loaded) await loadHistory(row)
  }
  /** 回到新对话首页，不分配业务 ID，也不创建服务端空会话。 */
  function startNew(): void {
    activeId.value = null
    actionError.value = ''
  }
  /** 加载当前会话更早记录，供页面在顶部保留阅读位置后插入旧消息。 */
  async function loadEarlier(): Promise<void> {
    if (activeConversation.value) await loadHistory(activeConversation.value, true)
  }
  /** 显式刷新当前会话，恢复其他窗口生成、失败或服务重启后的最新状态。 */
  async function refreshHistory(): Promise<void> {
    if (activeConversation.value) await loadHistory(activeConversation.value)
  }
  /** 软删除会话，失败保留目录和正文；本地生成中拒绝删除，跨窗口冲突交由后端确认。 */
  async function remove(id: string): Promise<void> {
    const row = conversations.value.find((item) => item.id === id)
    if (!row || row.running || row.deleting || !row.persisted) return
    const version = epoch
    const request = controller()
    row.deleting = true
    actionError.value = ''
    try {
      try {
        await deleteConversation(id, request.signal)
      } catch (error) {
        if (!(error instanceof ApiError && error.status === 404)) throw error
      }
      if (!current(version, row)) return
      histories.get(row)?.abort()
      conversations.value = conversations.value.filter((item) => item !== row)
      if (activeId.value === id) activeId.value = null
    } catch (error) {
      if (current(version, row)) actionError.value = explain(error)
    } finally {
      controllers.delete(request)
      if (current(version, row)) row.deleting = false
    }
  }
  /**
   * 发送一轮消息，首次省略会话 ID，收到 start 后绑定服务器身份，再更新公开过程及最终回答。
   * 每个会话允许一个在途请求；切换会话继续更新原对象，退出账号取消流并丢弃迟到结果。
   * 不自动重试可能已落库的输入；HTTP 冲突或不存在明确提示，部分回复保留为未完成。
   */
  async function send(text: string): Promise<boolean> {
    const content = text.trim()
    lastErrorCode.value = undefined
    if (!content || isSending.value || inputBlocked.value || !auth.isAuthenticated) return false
    if (!activeConversation.value) {
      // draft 只作为尚未收到 start 的界面键，绝不放进网络请求。
      const id = `draft-${++sequence}`
      conversations.value.unshift({
        id,
        title: Array.from(content).slice(0, 24).join(''),
        group: '今天',
        messages: [],
        loaded: true,
        persisted: false,
      })
      activeId.value = id
    }
    const row = activeConversation.value!
    const version = epoch
    const request = controller()
    const before = row.id
    const user: ChatMessage = {
      id: `user-${++sequence}`,
      role: 'user',
      blocks: [{ type: 'paragraph', text: content }],
    }
    row.messages.push(user, {
      id: `assistant-${sequence}`,
      role: 'assistant',
      status: 'pending',
      blocks: [],
    })
    const assistant = row.messages[row.messages.length - 1]!
    row.running = true
    row.localRevision = ++mutation
    const segments = new Map<string, string>()
    try {
      for await (const event of streamChatMessage(
        content,
        row.persisted ? row.id : undefined,
        request.signal,
      )) {
        if (!current(version, row)) return false
        if (event.type === 'start') {
          // 目录可能先于 SSE 返回同一条会话；绑定时移除重复条目，保留当前流的对象。
          conversations.value = conversations.value.filter(
            (item) => item === row || item.id !== event.conversationId,
          )
          row.id = event.conversationId
          row.persisted = true
          row.loaded = true
          user.id = `${event.turnId}-user`
          assistant.id = `${event.turnId}-assistant`
          if (activeId.value === before) activeId.value = row.id
          row.lastMessageAt = new Date().toISOString()
          row.group = group(row.lastMessageAt)
          row.localRevision = ++mutation
          sort()
          continue
        }
        updateActivity(assistant, event)
        assistant.status = 'streaming'
        if (event.type === 'delta') {
          segments.set(event.messageId, (segments.get(event.messageId) ?? '') + event.text)
          assistant.blocks = Array.from(segments.values(), (value) => ({
            type: 'paragraph',
            text: value,
          }))
        } else if (event.type === 'done') {
          assistant.blocks = [{ type: 'paragraph', text: event.reply }]
          assistant.status = 'complete'
          finishActivities(assistant, true)
        }
      }
      return true
    } catch (error) {
      if (!current(version, row)) return false
      finishActivities(assistant, false)
      assistant.status = 'error'
      assistant.error = explain(error)
      lastErrorCode.value = error instanceof ApiError ? error.code : undefined
      if (error instanceof ApiError && error.status === 404) row.unavailable = true
      if (error instanceof ApiError && error.status === 409) row.remoteRunning = true
      return false
    } finally {
      controllers.delete(request)
      if (current(version, row)) row.running = false
    }
  }
  return {
    draft,
    lastErrorCode,
    conversations,
    activeId,
    activeConversation,
    isSending,
    inputBlocked,
    listing,
    listError,
    listInitialized,
    nextCursor,
    actionError,
    loadConversations,
    select,
    startNew,
    clearLocal,
    send,
    loadEarlier,
    refreshHistory,
    remove,
  }
})
