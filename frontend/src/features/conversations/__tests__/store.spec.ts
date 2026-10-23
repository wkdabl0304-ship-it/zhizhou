/** 服务端会话回归：真实接口适配与 store 贯通，覆盖游标、历史还原、竞争和权限失效。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { createPinia, disposePinia, type Pinia } from 'pinia'
import { authenticate } from '@/__tests__/helpers/auth'
import { controlledStream, eventFrame, success } from '@/__tests__/helpers/chatStream'
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/features/auth/store'
import { LOGIN, CREDENTIALS } from '@/features/auth/__tests__/helpers'
import { A, B, info, turn, response, deferredResponse } from './helpers'

let pinia: Pinia
const fetchMock = vi.fn<typeof fetch>()
// 各用例以真实认证 store 建立账号，后续请求才进入各场景的服务端替身。
beforeEach(async () => {
  pinia = createPinia()
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  await authenticate(pinia, fetchMock)
})
// 释放 store 的全部取消控制器、令牌时钟与全局替身。
afterEach(() => {
  disposePinia(pinia)
  vi.unstubAllGlobals()
  sessionStorage.clear()
})

describe('会话目录与历史', () => {
  // 目录最近优先、历史每页正序；重复记录只展示一次，游标按原值编码传回。
  it('加载目录和更早历史，重叠页去重且较早消息排在前面', async () => {
    fetchMock
      .mockResolvedValueOnce(response({ items: [info(A)], next_cursor: 'older+/=' }))
      .mockResolvedValueOnce(
        response({
          items: [info(A), info(B, '更早话题', '2026-10-20T00:00:00Z')],
          next_cursor: null,
        }),
      )
      .mockResolvedValueOnce(
        response({ conversation: info(A), items: [turn(2)], next_cursor: 'history' }),
      )
      .mockResolvedValueOnce(
        response({ conversation: info(A), items: [turn(1), turn(2)], next_cursor: null }),
      )
      .mockResolvedValueOnce(
        response({ conversation: info(B), items: [turn(3)], next_cursor: null }),
      )
    const chat = useChatStore()
    await chat.loadConversations()
    await chat.loadConversations(true)
    expect(chat.conversations.map((row) => row.id)).toEqual([A, B])
    expect(String(fetchMock.mock.calls[1]![0])).toBe(
      '/api/conversations?limit=20&cursor=older%2B%2F%3D',
    )
    await chat.select(A)
    expect(chat.activeConversation?.messages[1]?.blocks).toEqual([
      { type: 'paragraph', text: '**回答2**' },
    ])
    await chat.loadEarlier()
    expect(chat.activeConversation?.messages.map((message) => message.id)).toEqual([
      'turn-1-user',
      'turn-1-assistant',
      'turn-2-user',
      'turn-2-assistant',
    ])
    expect(chat.activeConversation?.nextCursor).toBeNull()
    expect(new Headers(fetchMock.mock.calls[2]![1]?.headers).get('authorization')).toBe(
      'Bearer test-access-token',
    )
    await chat.select(B)
    await chat.select(A)
    // 读取 B 不破坏已缓存的 A，重新选择 A 不应重新请求。
    expect(chat.activeConversation?.messages).toHaveLength(4)
    expect(fetchMock).toHaveBeenCalledTimes(5)
  })

  // 历史中的工具成功和部分失败必须保留，running 快照不能伪装成本页的活跃连接。
  it('恢复工具时间线和未完成状态，刷新后允许继续聊天', async () => {
    const partial = {
      ...turn(1, 'running'),
      public_events: [
        { event: 'delta', data: { conversation_id: A, message_id: 'plan', text: '先检查环境' } },
        {
          event: 'tool_start',
          data: {
            conversation_id: A,
            tool_call_id: 'cmd',
            run_id: 'r',
            name: 'runner',
            kind: 'command',
            arguments: 'pwd',
          },
        },
      ],
    }
    fetchMock
      .mockResolvedValueOnce(response({ items: [info()], next_cursor: null }))
      .mockResolvedValueOnce(
        response({ conversation: info(), items: [partial], next_cursor: null }),
      )
      .mockResolvedValueOnce(response({ conversation: info(), items: [turn()], next_cursor: null }))
      .mockResolvedValueOnce(success(A, '继续后的回答', false))
    const chat = useChatStore()
    await chat.loadConversations()
    await chat.select(A)
    expect(chat.activeConversation?.remoteRunning).toBe(true)
    expect(chat.isSending).toBe(false)
    expect(chat.inputBlocked).toBe(true)
    expect(chat.activeConversation?.messages[1]?.activities?.[1]).toMatchObject({
      type: 'tool',
      status: 'interrupted',
    })
    expect(chat.activeConversation?.messages[1]?.error).toContain('仍在生成')
    expect(await chat.send('不应并发')).toBe(false)
    await chat.refreshHistory()
    expect(chat.inputBlocked).toBe(false)
    expect(await chat.send('继续')).toBe(true)
    expect(JSON.parse(fetchMock.mock.calls[3]![1]!.body as string)).toEqual({
      message: '继续',
      conversation_id: A,
    })
  })

  // 目录和历史都不能在 schema 或归属损坏时部分写入；错误可通过显式刷新恢复。
  it('损坏历史保持原状态并可重试，拒绝混入其他会话的公开事件', async () => {
    fetchMock
      .mockResolvedValueOnce(response({ items: [info()], next_cursor: null }))
      .mockResolvedValueOnce(
        response({
          conversation: info(),
          items: [
            {
              ...turn(),
              public_events: [
                {
                  event: 'delta',
                  data: { conversation_id: B, message_id: 'p', text: '别人的数据' },
                },
              ],
            },
          ],
          next_cursor: null,
        }),
      )
      .mockResolvedValueOnce(response({ conversation: info(), items: [turn()], next_cursor: null }))
    const chat = useChatStore()
    await chat.loadConversations()
    await chat.select(A)
    expect(chat.activeConversation?.messages).toHaveLength(0)
    expect(chat.activeConversation?.historyError).toContain('历史过程事件无效')
    expect(chat.inputBlocked).toBe(true)
    await chat.refreshHistory()
    expect(chat.activeConversation?.messages).toHaveLength(2)
    expect(chat.inputBlocked).toBe(false)
  })

  // 服务端忙时不乐观删除；删除成功后回到首页，其他会话仍在。
  it('软删除冲突保留正文，成功后移除选中会话', async () => {
    fetchMock
      .mockResolvedValueOnce(response({ items: [info(A), info(B)], next_cursor: null }))
      .mockResolvedValueOnce(response({ conversation: info(), items: [turn()], next_cursor: null }))
      .mockResolvedValueOnce(response(null, 409, 40901, '会话正在生成，请稍后重试'))
      .mockResolvedValueOnce(response(null))
    const chat = useChatStore()
    await chat.loadConversations()
    await chat.select(A)
    await chat.remove(A)
    expect(chat.activeId).toBe(A)
    expect(chat.actionError).toContain('正在生成')
    expect(chat.activeConversation?.messages).toHaveLength(2)
    await chat.remove(A)
    expect(chat.activeId).toBeNull()
    expect(chat.conversations.map((row) => row.id)).toEqual([B])
    expect(fetchMock.mock.calls[3]).toMatchObject([`/api/conversations/${A}`, { method: 'DELETE' }])
  })

  // 生成中的本地流禁止删除和历史刷新；初始目录迟到不能把刚收到 start 的会话覆盖掉。
  it('目录迟到不会移除新会话，生成期间拒绝删除及历史刷新', async () => {
    const directory = deferredResponse()
    const stream = controlledStream()
    fetchMock.mockReturnValueOnce(directory.promise).mockResolvedValueOnce(stream.response)
    const chat = useChatStore()
    const list = chat.loadConversations()
    const pending = chat.send('新任务')
    stream.push(eventFrame('start', { conversation_id: A }))
    await flushPromises()
    directory.resolve(response({ items: [], next_cursor: null }))
    await list
    await chat.remove(A)
    await chat.refreshHistory()
    expect(chat.conversations.map((row) => row.id)).toEqual([A])
    expect(fetchMock).toHaveBeenCalledTimes(2)
    stream.push(eventFrame('done', { conversation_id: A, message_id: 'answer', reply: '完成' }))
    await pending
  })

  // 账号切换取消旧读取；不遵守 AbortSignal 的替身也不能把迟到目录写入新账号。
  it('旧账号的迟到目录和 401 不能影响新登录账号', async () => {
    const old = deferredResponse()
    fetchMock.mockReturnValueOnce(old.promise)
    const chat = useChatStore()
    const pending = chat.loadConversations()
    const signal = fetchMock.mock.calls[0]![1]!.signal
    useAuthStore().logout()
    fetchMock.mockResolvedValueOnce(
      response({
        ...LOGIN,
        access_token: 'new-token',
        user: { ...LOGIN.user, id: B, username: 'another' },
      }),
    )
    await useAuthStore().login(CREDENTIALS)
    old.resolve(response(null, 401, 40101, '过期'))
    await pending
    expect(signal?.aborted).toBe(true)
    expect(useAuthStore().user?.username).toBe('another')
    expect(chat.conversations).toHaveLength(0)
    expect(chat.listError).toBe('')
  })

  // 当前令牌失效由公共认证层统一结束身份，不留下目录错误或其他账号缓存。
  it('当前业务请求 401 清除身份和会话缓存', async () => {
    fetchMock.mockResolvedValueOnce(response(null, 401, 40101, '登录过期'))
    const chat = useChatStore()
    await chat.loadConversations()
    expect(useAuthStore().isAuthenticated).toBe(false)
    expect(chat.conversations).toHaveLength(0)
    expect(chat.listInitialized).toBe(false)
  })

  // 目录失败保留重试入口，损坏游标不会被视为成功的空页。
  it('目录错误可重试，并拒绝未推进的游标', async () => {
    fetchMock
      .mockResolvedValueOnce(response({ items: [], next_cursor: '' }))
      .mockResolvedValueOnce(response({ items: [info()], next_cursor: 'same' }))
      .mockResolvedValueOnce(response({ items: [info(B)], next_cursor: 'same' }))
    const chat = useChatStore()
    await chat.loadConversations()
    expect(chat.listError).toContain('分页格式无效')
    await chat.loadConversations()
    await chat.loadConversations(true)
    expect(chat.listError).toContain('未推进')
    expect(chat.conversations.map((row) => row.id)).toEqual([A])
  })
})
