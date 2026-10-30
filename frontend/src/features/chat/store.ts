/** 聊天状态：管理服务端会话目录、游标历史和流式续聊；缓存随账号退出清除。 */
import { computed, nextTick, onScopeDispose, ref, watch, type Ref } from 'vue'
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
import type { ChatMessage, Conversation, ModelChangeConfirmation } from '@/features/chat/types'
import { lastReplyModel } from './model-changes'
import { finishActivities, updateActivity } from '@/features/chat/activity'
import { useModelSelectionStore } from '@/features/model-selection/store'
import {
  decodeSelection,
  selectionIssueLabels,
  validateSelection,
} from '@/features/model-selection/contract'
import type { ModelIdentity, ModelSelection } from '@/features/model-selection/types'
import { replacementSelection, useModelRecovery } from './useModelRecovery'
import {
  getConversationInfo,
  patchConversationTitle,
  patchModelSelection,
  recoverModelSelection,
} from '@/features/chat/api/conversations'
import { normalizeTitle, titleIssue } from './titles'

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
  const choices = useModelSelectionStore()
  const newSelection = ref<ModelSelection | null>(null)
  const selectionNotice = ref('')
  const selectionEditing = ref(false)
  const modelChangeConfirmation = ref<ModelChangeConfirmation | null>(null)
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
  const effectiveSelection = computed(() =>
    activeConversation.value
      ? (activeConversation.value.modelSelection ??
        (activeConversation.value.persisted
          ? (choices.options?.default_selection ?? null)
          : newSelection.value))
      : newSelection.value,
  )
  // 当前身份仅用于待发送的切换提示，已接受轮次始终由后端快照确认。
  const currentModel = computed<ModelIdentity | null>(() => {
    const model = choices.models.find(
      (item) => item.model_configuration_id === effectiveSelection.value?.model_configuration_id,
    )
    return model
      ? {
          model_configuration_id: model.model_configuration_id,
          catalog_model_id: model.catalog_model_id,
          display_name: model.display_name,
        }
      : null
  })
  const selectionProblem = computed(() => {
    const row = activeConversation.value,
      choice = effectiveSelection.value
    if (choices.error) return choices.error
    if (!choices.options) return '正在读取模型选项…'
    if (row?.selectionRecovering) return ''
    if (row?.selectionError)
      return row.modelSelectionIssue
        ? `${selectionIssueLabels[row.modelSelectionIssue]}；${row.selectionError}`
        : row.selectionError
    if (row?.modelSelectionIssue) return selectionIssueLabels[row.modelSelectionIssue]
    return validateSelection(
      choice,
      choices.models.find(
        (model) => model.model_configuration_id === choice?.model_configuration_id,
      ),
    )
  })
  const selectionReady = computed(
    () =>
      !selectionProblem.value &&
      !activeConversation.value?.selectionSaving &&
      !selectionEditing.value,
  )
  // 仅初始化尚无选择的新会话；刷新允许范围不能替换已有选择或将其降档。
  watch(
    () => choices.options,
    (options) => {
      if (!newSelection.value && options?.default_selection)
        newSelection.value = decodeSelection(options.default_selection)
    },
    { flush: 'sync', immediate: true },
  )
  watch(activeConversation, () => {
    draft.value = ''
    selectionEditing.value = false
  })
  // 确认只属于打开它的聊天，切换上下文立即撤销，不能把旧消息发到新会话。
  watch(
    activeId,
    () => {
      modelChangeConfirmation.value = null
    },
    { flush: 'sync' },
  )
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
  let selectionRead = 0
  let titleRead = 0

  useModelRecovery(
    () => ({
      row: activeConversation.value,
      selection: effectiveSelection.value,
      options: choices.options,
      loading: choices.loading,
      error: choices.error,
      editing: selectionEditing.value,
    }),
    recoverSelection,
  )

  /** 恢复活动上下文的失效模型，后端按版本裁决，草稿和消息不参与本次写入。 */
  async function recoverSelection(): Promise<void> {
    const row = activeConversation.value,
      selected = effectiveSelection.value
    if (!selected || !choices.options) return
    if (!row?.persisted) {
      const replacement = replacementSelection(choices.options, selected)
      if (replacement) await chooseSelection(replacement)
      return
    }
    const version = epoch,
      request = controller()
    row.selectionSaving = true
    row.selectionRecovering = true
    row.selectionError = ''
    try {
      for (let attempt = 0; attempt < 2; attempt += 1) {
        try {
          const info = await recoverModelSelection(
            row.id,
            row.modelSelectionVersion ?? 1,
            request.signal,
          )
          if (!current(version, row) || request.signal.aborted) return
          selectionMetadata(row, info, ++selectionRead)
          if (activeId.value === row.id) selectionNotice.value = ''
          if (
            !choices.models.some(
              (model) =>
                model.model_configuration_id === info.model_selection?.model_configuration_id,
            )
          )
            await choices.load()
          return
        } catch (error) {
          if (!current(version, row) || request.signal.aborted) return
          if (!(error instanceof ApiError && error.code === 40904 && attempt === 0)) throw error
          // 只在确认前发生版本竞争时重读一次；合法的远端选择优先，不覆盖另一窗口的决定。
          await refreshSelection(row, true)
          if (!current(version, row) || request.signal.aborted || row.selectionError) return
          if (
            !row.modelSelectionIssue &&
            !validateSelection(
              row.modelSelection ?? null,
              choices.models.find(
                (model) =>
                  model.model_configuration_id === row.modelSelection?.model_configuration_id,
              ),
            )
          ) {
            if (activeId.value === row.id) selectionNotice.value = ''
            return
          }
        }
      }
    } catch (error) {
      if (!current(version, row) || request.signal.aborted) return
      row.selectionError = explain(error)
      if (error instanceof ApiError && error.code === 40901) row.remoteRunning = true
      if (error instanceof ApiError && error.code === 40401) row.unavailable = true
    } finally {
      controllers.delete(request)
      if (current(version, row)) {
        row.selectionSaving = false
        row.selectionRecovering = false
      }
    }
  }

  /** 接受尚未过期的标题快照，编辑写入期间和手动保存以前发出的读取均不能覆盖新标题。 */
  function titleMetadata(row: Conversation, info: ConversationInfo, stamp: number): void {
    if (row.titleSaving || stamp < (row.titleRead ?? 0)) return
    row.title = info.title
    row.titleRead = stamp
  }
  /** 回答完成后同步后端已生成的标题；失败保留原标题，后续目录同步仍可恢复。 */
  async function synchronizeTitle(row: Conversation): Promise<void> {
    const version = epoch,
      stamp = ++titleRead,
      request = controller()
    try {
      const info = await getConversationInfo(row.id, request.signal)
      if (current(version, row) && !request.signal.aborted) titleMetadata(row, info, stamp)
    } catch {
      // 标题读取失败不影响已经完成的回答，也不重发聊天；重新可见时的目录同步会再次读取。
    } finally {
      controllers.delete(request)
    }
  }
  /** 保存自己的会话标题，允许生成中改名；只合并标题，不回滚并行更新的模型选择或正文。 */
  async function rename(id: string, value: string): Promise<boolean> {
    const row = conversations.value.find((item) => item.id === id)
    if (!row?.persisted || row.titleSaving || row.deleting || row.unavailable) return false
    row.titleError = titleIssue(value)
    if (row.titleError) return false
    const version = epoch,
      request = controller()
    row.titleSaving = true
    row.localRevision = ++mutation
    try {
      const info = await patchConversationTitle(id, normalizeTitle(value), request.signal)
      if (!current(version, row) || request.signal.aborted) return false
      row.title = info.title
      return true
    } catch (error) {
      if (current(version, row) && !request.signal.aborted) row.titleError = explain(error)
      return false
    } finally {
      controllers.delete(request)
      if (current(version, row)) {
        row.titleSaving = false
        row.titleRead = ++titleRead
        row.localRevision = ++mutation
      }
    }
  }

  /** 按确认版本与读取序号合并选择，返回是否接受快照，避免旧响应清除最新错误。 */
  function selectionMetadata(row: Conversation, info: ConversationInfo, stamp: number): boolean {
    if (
      info.model_selection_version < (row.modelSelectionVersion ?? 1) ||
      (info.model_selection_version === (row.modelSelectionVersion ?? 1) &&
        stamp < (row.selectionRead ?? 0))
    )
      return false
    row.modelSelection = info.model_selection ? decodeSelection(info.model_selection) : null
    row.modelSelectionVersion = info.model_selection_version
    row.modelSelectionIssue = info.model_selection_issue
    row.selectionRead = stamp
    return true
  }
  /** 刷新单个会话的选择有效性，不改写消息列表、侧栏顺序或其他会话。 */
  async function refreshSelection(
    row = activeConversation.value,
    duringRecovery = false,
  ): Promise<void> {
    if (!row?.persisted || (row.selectionSaving && !duringRecovery)) return
    const version = epoch,
      stamp = ++selectionRead,
      titleStamp = ++titleRead,
      request = controller()
    try {
      const info = await getConversationInfo(row.id, request.signal)
      if (current(version, row) && !request.signal.aborted) {
        titleMetadata(row, info, titleStamp)
        if (selectionMetadata(row, info, stamp)) row.selectionError = ''
      }
    } catch (error) {
      if (current(version, row) && !request.signal.aborted && stamp >= (row.selectionRead ?? 0)) {
        row.selectionRead = stamp
        row.selectionError = explain(error)
        if (error instanceof ApiError && error.code === 40401) row.unavailable = true
      }
    } finally {
      controllers.delete(request)
    }
  }
  /** 从管理页返回或窗口恢复时同步允许范围，失效选择由恢复协调器自动处理。 */
  async function refreshChoices(): Promise<void> {
    await Promise.all([choices.load(), refreshSelection()])
  }
  /** 新会话只修改本地选择；已有会话先 PATCH，成功后才改变确认值与版本。 */
  async function chooseSelection(selection: ModelSelection): Promise<boolean> {
    const row = activeConversation.value
    if (
      row?.running ||
      row?.remoteRunning ||
      row?.selectionSaving ||
      row?.loading ||
      row?.deleting ||
      row?.unavailable
    )
      return false
    const error = validateSelection(
      selection,
      choices.models.find(
        (model) => model.model_configuration_id === selection.model_configuration_id,
      ),
    )
    if (error) {
      if (row) row.selectionError = error
      return false
    }
    selectionNotice.value = ''
    if (!row?.persisted) {
      if (row) {
        row.modelSelection = decodeSelection(selection)
        row.modelSelectionIssue = null
        row.selectionError = ''
      } else newSelection.value = decodeSelection(selection)
      return true
    }
    const version = epoch,
      request = controller()
    row.selectionSaving = true
    row.selectionError = ''
    try {
      const info = await patchModelSelection(
        row.id,
        row.modelSelectionVersion ?? 1,
        decodeSelection(selection),
        request.signal,
      )
      if (!current(version, row) || request.signal.aborted) return false
      selectionMetadata(row, info, ++selectionRead)
      return true
    } catch (error) {
      if (current(version, row) && !request.signal.aborted) {
        row.selectionError = explain(error)
        if (error instanceof ApiError) {
          lastErrorCode.value = error.code
          if (error.code === 40901) row.remoteRunning = true
          if (error.code === 40401) row.unavailable = true
          if ([40904, 42201, 42202].includes(error.code ?? 0)) {
            if (activeId.value === row.id)
              selectionNotice.value = `${explain(error)}，请确认最新选择后重试`
            await Promise.all([choices.load(), refreshSelection(row, true)])
          }
        }
      }
      return false
    } finally {
      controllers.delete(request)
      if (current(version, row)) row.selectionSaving = false
    }
  }

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
  function metadata(
    row: Conversation,
    info: ConversationInfo,
    stamp: number,
    titleStamp: number,
  ): void {
    selectionMetadata(row, info, stamp)
    titleMetadata(row, info, titleStamp)
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
      modelSelection: info.model_selection,
      modelSelectionVersion: info.model_selection_version,
      modelSelectionIssue: info.model_selection_issue,
    }
  }
  /** 清空账号缓存并取消全部在途请求；这里只清理浏览器状态，不删除服务端会话。 */
  function clearLocal(): void {
    epoch += 1
    draft.value = ''
    newSelection.value = null
    modelChangeConfirmation.value = null
    selectionEditing.value = false
    selectionNotice.value = ''
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
    const choiceStamp = ++selectionRead
    const titleStamp = ++titleRead
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
        if ((row.localRevision ?? 0) <= stamp && !row.running)
          metadata(row, info, choiceStamp, titleStamp)
        return row
      })
      const retained = more
        ? conversations.value
        : conversations.value.filter(
            (row) =>
              row.id === activeId.value ||
              row.running ||
              row.titleSaving ||
              row.actionOpen ||
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
    const choiceStamp = ++selectionRead
    const titleStamp = ++titleRead
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
      metadata(row, page.conversation, choiceStamp, titleStamp)
      sort()
    } catch (error) {
      if (current(version, row)) {
        row.historyError = explain(error)
        if (error instanceof ApiError && error.code === 40401) row.unavailable = true
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
    if (activeId.value === row.id && row.rejectedDraft) {
      await nextTick()
      draft.value = row.rejectedDraft
    }
  }
  /** 回到新对话首页，不分配业务 ID，也不创建服务端空会话。 */
  function startNew(): void {
    activeId.value = null
    newSelection.value = choices.options?.default_selection
      ? decodeSelection(choices.options.default_selection)
      : null
    selectionNotice.value = ''
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
  async function remove(id: string): Promise<boolean> {
    const row = conversations.value.find((item) => item.id === id)
    if (!row || row.running || row.deleting || row.titleSaving || !row.persisted) return false
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
      if (!current(version, row)) return false
      histories.get(row)?.abort()
      conversations.value = conversations.value.filter((item) => item !== row)
      if (activeId.value === id) activeId.value = null
      return true
    } catch (error) {
      if (current(version, row)) actionError.value = explain(error)
      return false
    } finally {
      controllers.delete(request)
      if (current(version, row)) row.deleting = false
    }
  }
  /**
   * 发送一轮消息，首轮携带具体模型选择，续聊携带确认版本，收到 start 后绑定服务端身份。
   * 每个会话允许一个在途请求；切换会话继续更新原对象，退出账号取消流并丢弃迟到结果。
   * 不自动重试可能已落库的输入；HTTP 冲突或不存在明确提示，部分回复保留为未完成。
   */
  async function send(text: string, acceptedChange?: ModelChangeConfirmation): Promise<boolean> {
    const content = text.trim()
    lastErrorCode.value = undefined
    if (!content || isSending.value || inputBlocked.value || !auth.isAuthenticated) return false
    if (activeConversation.value?.selectionSaving || (choices.options && !selectionReady.value))
      return false
    const from = lastReplyModel(activeConversation.value?.messages ?? []),
      to = currentModel.value
    if (
      from &&
      to &&
      from.catalog_model_id !== to.catalog_model_id &&
      !(
        acceptedChange?.conversationId === activeId.value &&
        acceptedChange.from.catalog_model_id === from.catalog_model_id &&
        acceptedChange.to.catalog_model_id === to.catalog_model_id
      )
    ) {
      modelChangeConfirmation.value = {
        conversationId: activeId.value!,
        content,
        from: { ...from },
        to: { ...to },
      }
      return false
    }
    modelChangeConfirmation.value = null
    if (
      activeConversation.value?.persisted &&
      !activeConversation.value.modelSelection &&
      effectiveSelection.value
    ) {
      const target = activeConversation.value,
        owner = epoch
      // 存量会话首次保存会等待 HTTP，期间切换会话或退出不得把消息发到新的上下文。
      target.rejectedDraft = content
      const saved = await chooseSelection(effectiveSelection.value)
      if (owner !== epoch || activeConversation.value !== target) return false
      if (!saved) {
        await nextTick()
        if (owner === epoch && activeConversation.value === target && !draft.value)
          draft.value = content
        return false
      }
    }
    if (!activeConversation.value) {
      // draft 只作为尚未收到 start 的界面键，绝不放进网络请求。
      const id = `draft-${++sequence}`
      conversations.value.unshift({
        id,
        title: Array.from(normalizeTitle(content)).slice(0, 24).join(''),
        group: '今天',
        messages: [],
        loaded: true,
        persisted: false,
        modelSelection: effectiveSelection.value ? decodeSelection(effectiveSelection.value) : null,
        modelSelectionVersion: 1,
      })
      activeId.value = id
    }
    const row = activeConversation.value!
    const version = epoch
    const request = controller()
    const before = row.id
    const userMessage: ChatMessage = {
      id: `user-${++sequence}`,
      role: 'user',
      model: currentModel.value,
      modelReplyStarted: false,
      blocks: [{ type: 'paragraph', text: content }],
    }
    // 用户确认且本轮实际开始提交后才清空对应草稿，后续输入不随旧请求被清除。
    if (draft.value.trim() === content) draft.value = ''
    row.messages.push(userMessage, {
      id: `assistant-${sequence}`,
      role: 'assistant',
      status: 'pending',
      blocks: [],
    })
    // 流事件必须写入缓存中的响应式对象，临时原对象上的修改不会触发分界线重新计算。
    const user = row.messages[row.messages.length - 2]!
    const assistant = row.messages[row.messages.length - 1]!
    row.running = true
    row.rejectedDraft = ''
    row.selectionError = ''
    selectionNotice.value = ''
    row.localRevision = ++mutation
    const segments = new Map<string, string>()
    let started = false
    try {
      for await (const event of streamChatMessage(
        content,
        row.persisted ? row.id : undefined,
        request.signal,
        row.persisted
          ? { model_selection_version: row.modelSelectionVersion ?? 1 }
          : row.modelSelection
            ? { model_selection: decodeSelection(row.modelSelection) }
            : undefined,
      )) {
        if (!current(version, row)) return false
        if (event.type === 'start') {
          started = true
          row.modelSelection = event.modelSelection
          row.modelSelectionVersion = event.modelSelectionVersion
          row.modelSelectionIssue = null
          row.selectionRead = ++selectionRead
          if (event.model) user.model = event.model
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
        if (
          (event.type === 'delta' && event.text.length > 0) ||
          event.type === 'tool_call' ||
          event.type === 'done'
        )
          user.modelReplyStarted = true
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
          // 后端在 done 前完成标题阶段；独立读取不延长发送锁，也不替换本页消息。
          void synchronizeTitle(row)
        }
      }
      return true
    } catch (error) {
      if (!current(version, row)) return false
      if (
        !started &&
        error instanceof ApiError &&
        [40904, 42201, 42202, 50301].includes(error.code ?? 0)
      ) {
        row.messages = row.messages.filter(
          (message) => message.id !== user.id && message.id !== assistant.id,
        )
        row.rejectedDraft = content
        row.selectionError = explain(error)
        lastErrorCode.value = error.code
        const active = activeId.value === row.id
        const restoreId = row.persisted ? row.id : null
        if (active) selectionNotice.value = `${explain(error)}，消息未发送，请确认选择后重试`
        if (!row.persisted && active) {
          conversations.value = conversations.value.filter((item) => item.id !== row.id)
          activeId.value = null
        }
        await Promise.all([
          choices.load(),
          row.persisted ? refreshSelection(row) : Promise.resolve(),
        ])
        await nextTick()
        if (active && version === epoch && activeId.value === restoreId && !draft.value)
          draft.value = content
        return false
      }
      finishActivities(assistant, false)
      assistant.status = 'error'
      assistant.error = explain(error)
      lastErrorCode.value = error instanceof ApiError ? error.code : undefined
      if (error instanceof ApiError && error.code === 40401) row.unavailable = true
      if (error instanceof ApiError && error.code === 40901) row.remoteRunning = true
      return false
    } finally {
      controllers.delete(request)
      if (current(version, row)) row.running = false
    }
  }
  /** 撤销尚未发送的模型变化确认，消息仍保留在输入区。 */
  function cancelModelChange(): void {
    modelChangeConfirmation.value = null
  }
  /** 按已展示的模型身份确认发送；目标变化时重新询问，切换会话后不继续旧发送。 */
  async function confirmModelChange(): Promise<boolean> {
    const confirmation = modelChangeConfirmation.value
    if (!confirmation || confirmation.conversationId !== activeId.value) return false
    modelChangeConfirmation.value = null
    return send(confirmation.content, confirmation)
  }
  return {
    draft,
    effectiveSelection,
    currentModel,
    modelChangeConfirmation,
    cancelModelChange,
    confirmModelChange,
    selectionEditing,
    selectionProblem,
    selectionReady,
    selectionNotice,
    refreshChoices,
    chooseSelection,
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
    rename,
  }
})
