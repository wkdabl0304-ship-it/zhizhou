/** 会话模型选择状态回归：验证版本、独立选择、失效草稿、账号隔离与迟到响应。 */
import { beforeEach, expect, it, vi } from 'vitest'
import { createTestPinia } from '@tests/support/vitest/mount'
import { authenticate } from '@tests/support/vitest/auth'
import { deferredResponse, response } from '@tests/support/vitest/http'
import { eventFrame } from '@tests/support/vitest/chat'
import { sseResponse } from '@tests/support/vitest/sse'
import { modelOptionsData } from '@tests/support/data/model-selection'
import { A, B, info } from '@tests/support/data/chat'
import { useAuthStore } from '@/features/auth/store'
import { useModelSelectionStore } from '@/features/model-selection/store'
import { useChatStore } from '../../store'
const fetchMock = vi.fn<typeof fetch>()
beforeEach(async () => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  await authenticate(createTestPinia(), fetchMock)
})
/** 建立已有选择的两个会话和独立允许范围，避免依赖目录或历史读取。 */
function existing() {
  const data = modelOptionsData(),
    choices = useModelSelectionStore(),
    chat = useChatStore()
  choices.options = data
  chat.conversations = [A, B].map((id) => ({
    id,
    title: id,
    group: '今天',
    messages: [],
    persisted: true,
    loaded: true,
    modelSelection: structuredClone(data.default_selection),
    modelSelectionVersion: 3,
    modelSelectionIssue: null,
  }))
  chat.activeId = A
  return { chat, choices, data }
}
it('保存只更新原会话，旧读取不能覆盖新版本，同版本最新失效原因仍生效', async () => {
  const { chat, data } = existing(),
    old = deferredResponse()
  fetchMock.mockImplementation((url, init) => {
    if (String(url).endsWith('/options')) return Promise.resolve(response(data))
    if (init?.method === 'PATCH')
      return Promise.resolve(
        response({
          ...info(),
          model_selection: { ...data.default_selection, reasoning: { mode: 'off' } },
          model_selection_version: 4,
          model_selection_issue: null,
        }),
      )
    return old.promise
  })
  const reading = chat.refreshChoices()
  await chat.chooseSelection({
    model_configuration_id: data.default_selection!.model_configuration_id,
    reasoning: { mode: 'off' },
  })
  old.resolve(
    response({
      conversation: {
        ...info(),
        model_selection: data.default_selection,
        model_selection_version: 3,
        model_selection_issue: null,
      },
    }),
  )
  await reading
  expect(chat.activeConversation?.modelSelectionVersion).toBe(4)
  expect(chat.activeConversation?.modelSelection?.reasoning).toEqual({ mode: 'off' })
  await chat.select(B)
  expect(chat.effectiveSelection?.reasoning).toEqual({ mode: 'budget', budget_tokens: 4096 })
  await chat.select(A)
  fetchMock.mockImplementation(async (url) =>
    String(url).endsWith('/options')
      ? response(data)
      : response({
          conversation: {
            ...info(),
            model_selection: chat.effectiveSelection,
            model_selection_version: 4,
            model_selection_issue: 'model_disabled',
          },
        }),
  )
  await chat.refreshChoices()
  expect(chat.selectionProblem).toContain('已停用')
  expect(chat.selectionReady).toBe(false)
})
it('选择版本冲突不伪装为正在生成，保留消息草稿且不自动重发', async () => {
  const { chat, data } = existing()
  fetchMock.mockImplementation(async (url) => {
    if (url === '/api/chat') return response(null, 409, 40904, '会话选择已变更')
    if (String(url).endsWith('/options')) return response(data)
    return response({
      conversation: {
        ...info(),
        model_selection: data.default_selection,
        model_selection_version: 4,
        model_selection_issue: null,
      },
    })
  })
  await chat.send('冲突时保留的消息')
  expect(chat.draft).toBe('冲突时保留的消息')
  expect(chat.activeConversation?.messages).toEqual([])
  expect(chat.activeConversation?.remoteRunning).not.toBe(true)
  expect(chat.activeConversation?.modelSelectionVersion).toBe(4)
  expect(fetchMock.mock.calls.filter(([url]) => url === '/api/chat')).toHaveLength(1)
  const write = fetchMock.mock.calls.find(([url]) => url === '/api/chat')!
  expect(JSON.parse(String(write[1]?.body))).toEqual({
    message: '冲突时保留的消息',
    conversation_id: A,
    model_selection_version: 3,
  })
})
it('退出时取消选择保存，迟到的成功结果不能恢复旧账号会话', async () => {
  const { chat, data } = existing(),
    pending = deferredResponse()
  fetchMock.mockReturnValueOnce(pending.promise)
  const saving = chat.chooseSelection({
      model_configuration_id: data.default_selection!.model_configuration_id,
      reasoning: { mode: 'off' },
    }),
    signal = fetchMock.mock.lastCall?.[1]?.signal
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
  expect(await saving).toBe(false)
  expect(chat.conversations).toEqual([])
})

it('首轮选择失效时不留下临时会话，并保留选择和消息草稿供手动重试', async () => {
  const data = modelOptionsData(),
    choices = useModelSelectionStore(),
    chat = useChatStore()
  choices.options = data
  fetchMock.mockImplementation(async (url) =>
    String(url).endsWith('/chat')
      ? response(null, 422, 42201, '模型不可选')
      : response({ default_selection: null, providers: [] }),
  )
  chat.draft = '首次发送需保留的草稿'
  expect(await chat.send(chat.draft)).toBe(false)
  expect(chat.conversations).toHaveLength(0)
  expect(chat.activeId).toBe(null)
  expect(chat.draft).toBe('首次发送需保留的草稿')
  expect(chat.effectiveSelection).toEqual(data.default_selection)
  expect(chat.selectionReady).toBe(false)
  expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/chat'))).toHaveLength(1)
})

it('冲突恢复期间切换会话，不把原会话待重试的消息草稿写入新会话', async () => {
  const { chat, data } = existing(),
    recovery = deferredResponse()
  fetchMock.mockImplementation(async (url) => {
    if (String(url).endsWith('/chat')) return response(null, 409, 40904, '会话选择已变更')
    if (String(url).endsWith('/options')) return recovery.promise
    return response({
      conversation: {
        ...info(),
        model_selection: data.default_selection,
        model_selection_version: 4,
        model_selection_issue: null,
      },
    })
  })
  const sending = chat.send('原会话的待重试消息')
  await vi.waitFor(() => expect(chat.selectionNotice).toContain('消息未发送'))
  await chat.select(B)
  recovery.resolve(response(data))
  await sending
  expect(chat.activeId).toBe(B)
  expect(chat.draft).toBe('')
  await chat.select(A)
  expect(chat.draft).toBe('原会话的待重试消息')
})

it('旧读取错误不阻塞新确认，旧成功也不能清除同版本最新的读取错误', async () => {
  const { chat, data } = existing(),
    reading = deferredResponse()
  fetchMock.mockImplementation(async (url, init) => {
    if (String(url).endsWith('/options')) return response(data)
    if (init?.method === 'PATCH')
      return response({
        ...info(),
        model_selection: { ...data.default_selection, reasoning: { mode: 'off' } },
        model_selection_version: 4,
        model_selection_issue: null,
      })
    return reading.promise
  })
  const old = chat.refreshChoices()
  expect(
    await chat.chooseSelection({ ...data.default_selection!, reasoning: { mode: 'off' } }),
  ).toBe(true)
  reading.resolve(response(null, 500, 50000, '较早的读取失败'))
  await old
  expect(chat.selectionReady).toBe(true)
  const earlier = deferredResponse(),
    newest = deferredResponse()
  let calls = 0
  fetchMock.mockImplementation(async (url) =>
    String(url).endsWith('/options')
      ? response(data)
      : ++calls === 1
        ? earlier.promise
        : newest.promise,
  )
  const first = chat.refreshChoices(),
    second = chat.refreshChoices()
  newest.resolve(response(null, 500, 50000, '最新选择状态读取失败'))
  await second
  earlier.resolve(
    response({
      conversation: {
        ...info(),
        model_selection: data.default_selection,
        model_selection_version: 4,
        model_selection_issue: null,
      },
    }),
  )
  await first
  expect(chat.selectionProblem).toBe('最新选择状态读取失败')
  expect(chat.selectionReady).toBe(false)
  expect(chat.effectiveSelection?.reasoning).toEqual({ mode: 'off' })
})

it('存量空选择先保存预览的默认值，再按已确认版本续聊，start 保留服务端确认', async () => {
  const { chat, data } = existing(),
    saving = deferredResponse()
  chat.activeConversation!.modelSelection = null
  fetchMock.mockImplementation(async (_url, init) =>
    init?.method === 'PATCH'
      ? saving.promise
      : sseResponse(
          eventFrame('start', {
            conversation_id: A,
            turn_id: 'legacy-turn',
            is_new: false,
            model_selection: data.default_selection,
            model_selection_version: 4,
          }) +
            eventFrame('done', {
              conversation_id: A,
              message_id: 'legacy-reply',
              reply: '已沿用保存的模型选择',
            }),
        ),
  )
  const sending = chat.send('存量会话继续聊')
  expect(fetchMock.mock.calls).toHaveLength(1)
  expect(fetchMock.mock.calls[0]?.[1]?.method).toBe('PATCH')
  saving.resolve(
    response({
      ...info(),
      model_selection: data.default_selection,
      model_selection_version: 4,
      model_selection_issue: null,
    }),
  )
  expect(await sending).toBe(true)
  expect(fetchMock.mock.calls).toHaveLength(2)
  expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
    model_selection_version: 3,
    model_selection: data.default_selection,
  })
  expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({
    message: '存量会话继续聊',
    conversation_id: A,
    model_selection_version: 4,
  })
  expect(chat.activeConversation?.modelSelectionVersion).toBe(4)
  expect(chat.activeConversation?.messages.at(-1)?.status).toBe('complete')
})

it('存量会话保存选择期间切换会话，不串发消息，原会话保留待重试草稿', async () => {
  const { chat, data } = existing(),
    saving = deferredResponse()
  chat.activeConversation!.modelSelection = null
  fetchMock.mockReturnValue(saving.promise)
  const sending = chat.send('只属于原存量会话的消息')
  await chat.select(B)
  saving.resolve(
    response({
      ...info(),
      model_selection: data.default_selection,
      model_selection_version: 4,
      model_selection_issue: null,
    }),
  )
  expect(await sending).toBe(false)
  expect(chat.activeId).toBe(B)
  expect(chat.activeConversation?.messages).toEqual([])
  expect(fetchMock.mock.calls).toHaveLength(1)
  await chat.select(A)
  expect(chat.draft).toBe('只属于原存量会话的消息')
})

it('存量会话保存选择期间退出，迟到响应不把旧账号内容恢复成新草稿', async () => {
  const { chat, data } = existing(),
    saving = deferredResponse()
  chat.activeConversation!.modelSelection = null
  fetchMock.mockReturnValue(saving.promise)
  const sending = chat.send('退出前的私有内容')
  useAuthStore().logout()
  saving.resolve(
    response({
      ...info(),
      model_selection: data.default_selection,
      model_selection_version: 4,
      model_selection_issue: null,
    }),
  )
  expect(await sending).toBe(false)
  expect(chat.draft).toBe('')
  expect(chat.conversations).toEqual([])
  expect(fetchMock.mock.calls).toHaveLength(1)
})

it('同版本读取只采用最新失效状态，选择冲突恢复期间保持保存锁', async () => {
  const { chat, data } = existing(),
    older = deferredResponse(),
    latest = deferredResponse()
  let reads = 0
  fetchMock.mockImplementation((url) =>
    String(url).endsWith('/options')
      ? Promise.resolve(response(data))
      : ++reads === 1
        ? older.promise
        : latest.promise,
  )
  const first = chat.refreshChoices(),
    second = chat.refreshChoices()
  latest.resolve(
    response({
      conversation: {
        ...info(),
        model_selection: data.default_selection,
        model_selection_version: 3,
        model_selection_issue: 'model_disabled',
      },
    }),
  )
  await second
  older.resolve(
    response({
      conversation: {
        ...info(),
        model_selection: data.default_selection,
        model_selection_version: 3,
        model_selection_issue: null,
      },
    }),
  )
  await first
  expect(chat.activeConversation?.modelSelectionIssue).toBe('model_disabled')
  const recovery = deferredResponse()
  fetchMock.mockImplementation(async (url, init) => {
    if (init?.method === 'PATCH') return response(null, 409, 40904, '选择版本冲突')
    if (String(url).endsWith('/options')) return recovery.promise
    return response({
      conversation: {
        ...info(),
        model_selection: data.default_selection,
        model_selection_version: 4,
        model_selection_issue: null,
      },
    })
  })
  const saving = chat.chooseSelection({
    model_configuration_id: data.default_selection!.model_configuration_id,
    reasoning: { mode: 'off' },
  })
  await vi.waitFor(() => expect(chat.selectionNotice).toContain('选择版本冲突'))
  expect(chat.activeConversation?.selectionSaving).toBe(true)
  expect(await chat.chooseSelection(data.default_selection!)).toBe(false)
  recovery.resolve(response(data))
  await saving
  expect(chat.activeConversation?.selectionSaving).toBe(false)
})
