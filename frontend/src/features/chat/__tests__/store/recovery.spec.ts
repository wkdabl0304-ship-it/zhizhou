/** 自动恢复回归：失效选择由后端裁决，保留草稿、账号隔离与生成中的模型归属。 */
import { beforeEach, expect, it, vi } from 'vitest'
import { createTestPinia } from '@tests/support/vitest/mount'
import { authenticate } from '@tests/support/vitest/auth'
import { deferredResponse, response } from '@tests/support/vitest/http'
import { modelOptionsData } from '@tests/support/data/model-selection'
import { A, info } from '@tests/support/data/chat'
import { useChatStore } from '../../store'
import { useModelSelectionStore } from '@/features/model-selection/store'
import { useAuthStore } from '@/features/auth/store'

const fetchMock = vi.fn<typeof fetch>()
beforeEach(async () => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
  await authenticate(createTestPinia(), fetchMock)
})

/** 建立原方案已删除的活动会话，保留原消息和输入以便验证恢复不会破坏内容。 */
function deletedConversation(running = false) {
  const choices = useModelSelectionStore(),
    chat = useChatStore(),
    data = modelOptionsData()
  const old = structuredClone(data.default_selection!)
  data.providers[0]!.models[0]!.model_configuration_id = 'replacement'
  data.default_selection!.model_configuration_id = 'replacement'
  choices.options = data
  chat.conversations = [
    {
      id: A,
      title: '原聊天',
      group: '今天',
      persisted: true,
      loaded: true,
      running,
      modelSelection: old,
      modelSelectionVersion: 3,
      modelSelectionIssue: 'model_deleted',
      messages: [{ id: 'kept', role: 'user', blocks: [{ type: 'paragraph', text: '原消息' }] }],
    },
  ]
  chat.activeId = A
  return { choices, chat, data }
}

it('删除原模型后自动保存替代选择，保留草稿且不发送聊天', async () => {
  const { chat, data } = deletedConversation()
  const pending = deferredResponse()
  fetchMock.mockReturnValue(pending.promise)
  await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
  chat.draft = '待发送的草稿'
  expect(chat.selectionReady).toBe(false)
  expect(chat.selectionProblem).toBe('')
  pending.resolve(
    response({
      ...info(),
      model_selection: data.default_selection,
      model_selection_version: 4,
      model_selection_issue: null,
    }),
  )
  await vi.waitFor(() => expect(chat.activeConversation?.modelSelectionVersion).toBe(4))
  expect(chat.effectiveSelection).toEqual(data.default_selection)
  expect(chat.draft).toBe('待发送的草稿')
  expect(chat.activeConversation?.messages).toHaveLength(1)
  expect(chat.selectionReady).toBe(true)
  expect(fetchMock).toHaveBeenCalledTimes(1)
  expect(JSON.parse(String(fetchMock.mock.calls[0]![1]?.body))).toEqual({
    model_selection_version: 3,
    model_selection: null,
  })
})

it('生成时延后恢复，结束后自动处理，退出后迟到响应不得恢复缓存', async () => {
  const { chat, data } = deletedConversation(true),
    pending = deferredResponse()
  fetchMock.mockReturnValue(pending.promise)
  await Promise.resolve()
  expect(fetchMock).not.toHaveBeenCalled()
  chat.activeConversation!.running = false
  await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
  const signal = fetchMock.mock.calls[0]![1]?.signal
  useAuthStore().logout()
  expect(signal?.aborted).toBe(true)
  pending.resolve(
    response({
      ...info(),
      model_selection: data.default_selection,
      model_selection_version: 4,
      model_selection_issue: null,
    }),
  )
  await Promise.resolve()
  expect(chat.conversations).toEqual([])
})

it('恢复失败保留真实错误且不循环重试，没有可用模型时也不重复请求', async () => {
  const { chat, choices } = deletedConversation()
  fetchMock.mockResolvedValue(response(null, 503, 50301, '没有可用模型'))
  await vi.waitFor(() => expect(chat.selectionProblem).toContain('没有可用模型'))
  await Promise.resolve()
  expect(fetchMock).toHaveBeenCalledTimes(1)
  choices.options = { default_selection: null, providers: [] }
  await Promise.resolve()
  expect(fetchMock).toHaveBeenCalledTimes(1)
  expect(chat.activeConversation?.messages).toHaveLength(1)
})

it('恢复版本竞争时接受另一窗口已确认的合法选择，不再覆盖或重发消息', async () => {
  const { chat, data } = deletedConversation()
  fetchMock.mockImplementation(async (_url, init) =>
    init?.method === 'PATCH'
      ? response(null, 409, 40904, '选择版本冲突')
      : response({
          conversation: {
            ...info(),
            model_selection: data.default_selection,
            model_selection_version: 5,
            model_selection_issue: null,
          },
        }),
  )
  await vi.waitFor(() => expect(chat.activeConversation?.modelSelectionVersion).toBe(5))
  expect(chat.effectiveSelection).toEqual(data.default_selection)
  expect(chat.selectionReady).toBe(true)
  expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'PATCH')).toHaveLength(1)
  expect(fetchMock.mock.calls.some(([url]) => url === '/api/chat')).toBe(false)
})

it('并行窗口的新版本仍失效时只重试一次，使用最新版本恢复', async () => {
  const { chat, data } = deletedConversation(),
    old = chat.effectiveSelection
  fetchMock.mockImplementation(async (_url, init) => {
    if (init?.method === 'PATCH') {
      const body = JSON.parse(String(init.body))
      return body.model_selection_version === 3
        ? response(null, 409, 40904, '选择版本冲突')
        : response({
            ...info(),
            model_selection: data.default_selection,
            model_selection_version: 5,
            model_selection_issue: null,
          })
    }
    return response({
      conversation: {
        ...info(),
        model_selection: old,
        model_selection_version: 4,
        model_selection_issue: 'model_deleted',
      },
    })
  })
  await vi.waitFor(() => expect(chat.activeConversation?.modelSelectionVersion).toBe(5))
  const versions = fetchMock.mock.calls
    .filter(([, init]) => init?.method === 'PATCH')
    .map(([, init]) => JSON.parse(String(init?.body)).model_selection_version)
  expect(versions).toEqual([3, 4])
  expect(chat.selectionReady).toBe(true)
})

it('新对话的原方案删除后只更新本地选择，保留草稿且不创建空会话', async () => {
  const chat = useChatStore(),
    choices = useModelSelectionStore(),
    initial = modelOptionsData()
  choices.options = initial
  await vi.waitFor(() => expect(chat.effectiveSelection).toEqual(initial.default_selection))
  chat.draft = '还没有发送'
  const replacement = modelOptionsData()
  replacement.default_selection!.model_configuration_id = 'new-model'
  replacement.providers[0]!.models[0]!.model_configuration_id = 'new-model'
  choices.options = replacement
  await vi.waitFor(() => expect(chat.effectiveSelection?.model_configuration_id).toBe('new-model'))
  expect(chat.draft).toBe('还没有发送')
  expect(chat.conversations).toEqual([])
  expect(fetchMock).not.toHaveBeenCalled()
})
