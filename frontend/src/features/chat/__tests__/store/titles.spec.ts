/** 会话标题状态回归：自动同步、手动保存、读写竞争、模型独立性和账号隔离。 */
import { beforeEach, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { createTestPinia } from '@tests/support/vitest/mount'
import { authenticate } from '@tests/support/vitest/auth'
import { response, deferredResponse } from '@tests/support/vitest/http'
import { success } from '@tests/support/vitest/chat'
import { A, B, info, turn } from '@tests/support/data/chat'
import { modelOptionsData } from '@tests/support/data/model-selection'
import { useAuthStore } from '@/features/auth/store'
import { useChatStore } from '../../store'

const fetchMock = vi.fn<typeof fetch>()
beforeEach(async () => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  await authenticate(createTestPinia(), fetchMock)
})
/** 准备两个已保存会话，直接验证状态边界而不混入首次目录加载。 */
function prepare() {
  const chat = useChatStore()
  chat.conversations = [A, B].map((id) => ({
    id,
    title: id === A ? '原标题' : '另一个话题',
    group: '今天',
    messages: [],
    persisted: true,
    loaded: true,
  }))
  chat.activeId = A
  return { chat, row: chat.conversations[0]! }
}

it('操作弹窗打开时保留较早会话，关闭后允许目录按最新一页收敛', async () => {
  const { chat, row } = prepare()
  chat.activeId = B
  row.actionOpen = true
  fetchMock.mockImplementation(async () => response({ items: [info(B)], next_cursor: null }))
  await chat.loadConversations()
  expect(chat.conversations).toContain(row)
  row.actionOpen = false
  await chat.loadConversations()
  expect(chat.conversations).not.toContain(row)
})

it('生成期间可规范化保存手动标题，重复保存和删除被阻止，模型版本和消息不回滚', async () => {
  const pending = deferredResponse(),
    { chat, row } = prepare()
  fetchMock.mockReturnValue(pending.promise)
  row.running = true
  row.modelSelectionVersion = 7
  const messages = row.messages
  const saving = chat.rename(A, '  手动\n\t标题  ')
  expect(row.titleSaving).toBe(true)
  expect(row.title).toBe('原标题')
  expect(await chat.rename(A, '重复')).toBe(false)
  await chat.remove(A)
  expect(fetchMock).toHaveBeenCalledTimes(1)
  expect(JSON.parse(String(fetchMock.mock.calls[0]![1]?.body))).toEqual({ title: '手动 标题' })
  pending.resolve(response(info(A, '手动 标题')))
  expect(await saving).toBe(true)
  expect(row.title).toBe('手动 标题')
  expect(row.running).toBe(true)
  expect(row.modelSelectionVersion).toBe(7)
  expect(row.messages).toBe(messages)
})

it('空白和超长标题不写入，100 个表情可保存，同名保存仍会调用接口', async () => {
  const { chat, row } = prepare()
  expect(await chat.rename(A, '\u0085\n  ')).toBe(false)
  expect(await chat.rename(A, '舟'.repeat(101))).toBe(false)
  expect(fetchMock).not.toHaveBeenCalled()
  fetchMock.mockImplementation(async (_url, init) =>
    response(info(A, JSON.parse(String(init?.body)).title)),
  )
  expect(await chat.rename(A, '🚣'.repeat(100))).toBe(true)
  expect(Array.from(row.title)).toHaveLength(100)
  expect(await chat.rename(A, row.title)).toBe(true)
  expect(fetchMock).toHaveBeenCalledTimes(2)
})

it('保存失败保留原标题并可重试，账号退出取消写入且迟到结果不能恢复目录', async () => {
  const { chat, row } = prepare()
  fetchMock.mockResolvedValueOnce(response(null, 500, 50000, '保存失败'))
  expect(await chat.rename(A, '修改')).toBe(false)
  expect(row.title).toBe('原标题')
  expect(row.titleError).toContain('保存失败')
  expect(row.titleSaving).toBe(false)
  const pending = deferredResponse()
  fetchMock.mockReturnValueOnce(pending.promise)
  const saving = chat.rename(A, '重试标题')
  const signal = fetchMock.mock.calls[1]![1]!.signal
  useAuthStore().logout()
  expect(signal?.aborted).toBe(true)
  pending.resolve(response(info(A, '重试标题')))
  expect(await saving).toBe(false)
  expect(chat.conversations).toHaveLength(0)
})

it.each(['history', 'directory', 'selection'])(
  '较早的 %s 响应不能覆盖刚保存的手动标题',
  async (kind) => {
    const { chat, row } = prepare(),
      old = deferredResponse()
    fetchMock.mockImplementation(async (url, init) => {
      if (String(url).endsWith('/options')) return response(modelOptionsData())
      return init?.method === 'PATCH' ? response(info(A, '手动标题')) : old.promise
    })
    const reading =
      kind === 'history'
        ? chat.refreshHistory()
        : kind === 'directory'
          ? chat.loadConversations()
          : chat.refreshChoices()
    await chat.rename(A, '手动标题')
    old.resolve(
      response(
        kind === 'directory'
          ? { items: [info(A, '旧标题')], next_cursor: null }
          : { conversation: info(A, '旧标题'), items: [turn()], next_cursor: null },
      ),
    )
    await reading
    expect(row.title).toBe('手动标题')
  },
)

it('改名期间启动的读取也不能在保存成功后回滚标题，后台目录刷新保留正在改名的旧会话', async () => {
  const { chat, row } = prepare(),
    patch = deferredResponse(),
    read = deferredResponse()
  fetchMock.mockImplementation(async (_url, init) =>
    init?.method === 'PATCH' ? patch.promise : read.promise,
  )
  chat.activeId = B
  const saving = chat.rename(A, '新标题')
  const listing = chat.loadConversations()
  read.resolve(response({ items: [info(B)], next_cursor: null }))
  await listing
  expect(chat.conversations).toContain(row)
  patch.resolve(response(info(A, '新标题')))
  expect(await saving).toBe(true)
  expect(row.title).toBe('新标题')
})

it('done 后同步真正的自动标题，切换会话不抢回活动页、不覆盖消息和输入草稿', async () => {
  const { chat, row } = prepare(),
    title = deferredResponse()
  fetchMock.mockImplementation(async (_url, init) =>
    init?.method === 'POST' ? success(A, '成功回答', false) : title.promise,
  )
  expect(await chat.send('继续问题')).toBe(true)
  expect(row.running).toBe(false)
  expect(row.messages[1]?.status).toBe('complete')
  chat.activeId = B
  await flushPromises()
  chat.draft = '另一个会话的草稿'
  title.resolve(response({ conversation: info(A, 'AI 概括的主题'), items: [], next_cursor: null }))
  await flushPromises()
  expect(row.title).toBe('AI 概括的主题')
  expect(row.messages).toHaveLength(2)
  expect(chat.activeId).toBe(B)
  expect(chat.activeConversation?.title).toBe('另一个话题')
  expect(chat.draft).toBe('另一个会话的草稿')
})

it('改名期间发起的历史读取，晚于保存返回也不能覆盖手动标题', async () => {
  const { chat, row } = prepare(),
    patch = deferredResponse(),
    read = deferredResponse()
  fetchMock.mockImplementation(async (_url, init) =>
    init?.method === 'PATCH' ? patch.promise : read.promise,
  )
  const saving = chat.rename(A, '优先手动标题')
  const reading = chat.refreshHistory()
  patch.resolve(response(info(A, '优先手动标题')))
  expect(await saving).toBe(true)
  read.resolve(
    response({ conversation: info(A, '过时的自动标题'), items: [turn()], next_cursor: null }),
  )
  await reading
  expect(row.title).toBe('优先手动标题')
})

it('自动标题同步失败不把成功回答变为失败，后续目录读取可恢复', async () => {
  const { chat, row } = prepare()
  fetchMock.mockImplementation(async (_url, init) => {
    if (init?.method === 'POST') return success(A, '成功回答', false)
    throw new TypeError('offline')
  })
  expect(await chat.send('继续问题')).toBe(true)
  await flushPromises()
  expect(row.messages[1]?.status).toBe('complete')
  expect(row.title).toBe('原标题')
  fetchMock.mockResolvedValue(response({ items: [info(A, '已恢复的标题')], next_cursor: null }))
  await chat.loadConversations()
  expect(row.title).toBe('已恢复的标题')
})
