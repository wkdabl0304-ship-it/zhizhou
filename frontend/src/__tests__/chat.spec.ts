/** 聊天请求回归：用 fetch 替身验证接口契约、临时会话、并发隔离及失败恢复，不调用模型。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useChatStore } from '@/stores/chat'

const fetchMock = vi.fn<typeof fetch>()

/** 构造与真实统一响应一致的成功结果，回显请求所属的 thread_id。 */
function success(threadId: string, reply = '后端真实格式的回复'): Response {
  return new Response(
    JSON.stringify({ code: 0, message: '成功', data: { reply, thread_id: threadId } }),
  )
}

// 每个测试隔离 Pinia 和网络替身，不访问真实后端或共享可变状态。
beforeEach(() => {
  setActivePinia(createPinia())
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  // 默认回显实际请求标识，同时断言请求体确实是合法 JSON。
  fetchMock.mockImplementation(async (_url, init) => {
    const body = JSON.parse(init!.body as string) as { thread_id: string }
    return success(body.thread_id)
  })
})

// 撤销全局替身，避免影响其他组件测试。
afterEach(() => vi.unstubAllGlobals())

describe('后端聊天状态', () => {
  // 空白不应创建会话，也不应请求服务。
  it('空白发送不改变首页与会话列表', async () => {
    const chat = useChatStore()
    expect(await chat.send(' \n\t ')).toBe(false)
    expect(chat.activeId).toBeNull()
    expect(chat.conversations).toHaveLength(0)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  // 同一会话的多轮消息复用随机标识，展示来自后端的文本而非演示回复。
  it('POST 消息和 thread_id，多轮对话复用标识', async () => {
    const chat = useChatStore()
    expect(await chat.send('  请帮我整理工作计划  ')).toBe(true)
    const id = chat.activeId!
    expect(id).toMatch(/^[a-f0-9-]{32,36}$/)
    expect(fetchMock).toHaveBeenLastCalledWith('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: '请帮我整理工作计划', thread_id: id }),
    })
    expect(chat.activeConversation?.title).toBe('请帮我整理工作计划')
    expect(chat.activeConversation?.messages[1]).toMatchObject({
      status: 'complete',
      blocks: [{ type: 'paragraph', text: '后端真实格式的回复' }],
    })
    expect(chat.activeConversation?.messages[1]?.demo).toBeUndefined()
    await chat.send('继续聊聊')
    expect(chat.activeId).toBe(id)
    expect(chat.activeConversation?.messages).toHaveLength(4)
    expect(JSON.parse(fetchMock.mock.calls[1]![1]!.body as string).thread_id).toBe(id)
  })

  // 新建会话和新页面分别获得随机标识；切换旧会话不改变其后端历史标识。
  it('新建和刷新后使用新标识，已有会话仍可切回', async () => {
    const chat = useChatStore()
    await chat.send('旧话题')
    const oldId = chat.activeId!
    chat.startNew()
    expect(chat.activeConversation).toBeUndefined()
    await chat.send('新话题')
    expect(chat.activeId).not.toBe(oldId)
    chat.select(oldId)
    chat.select('missing')
    expect(chat.activeId).toBe(oldId)
    await chat.send('继续旧话题')
    expect(chat.activeConversation?.messages).toHaveLength(4)
    setActivePinia(createPinia())
    const fresh = useChatStore()
    expect(fresh.conversations).toHaveLength(0)
    await fresh.send('页面重载')
    expect(fresh.activeId).not.toBe(oldId)
  })

  // 可控 Promise 模拟慢请求；释放后验证回复落在原会话，且等待中重复发送不会调用服务。
  it('阻止同会话并发，并在切换后更新原会话占位', async () => {
    let resolveReply!: (response: Response) => void
    fetchMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveReply = resolve
        }),
    )
    const chat = useChatStore()
    const pending = chat.send('慢消息')
    const oldId = chat.activeId!
    expect(chat.isSending).toBe(true)
    expect(chat.activeConversation?.messages[1]?.status).toBe('pending')
    expect(await chat.send('重复发送')).toBe(false)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    chat.startNew()
    await chat.send('另一个会话')
    const newId = chat.activeId
    chat.select(oldId)
    expect(chat.isSending).toBe(true)
    chat.select(newId!)
    resolveReply(success(oldId, '迟到的回复'))
    await pending
    expect(chat.activeId).toBe(newId)
    expect(chat.activeConversation?.messages[1]?.blocks).not.toContainEqual({
      type: 'paragraph',
      text: '迟到的回复',
    })
    chat.select(oldId)
    expect(chat.activeConversation?.messages[1]?.blocks).toEqual([
      { type: 'paragraph', text: '迟到的回复' },
    ])
    expect(chat.isSending).toBe(false)
  })

  // 覆盖 HTTP 错误、HTTP 200 业务失败、协议格式错误与断网；均保留用户消息并允许继续发送。
  it.each(['http', 'business', 'invalid-json', 'invalid-data', 'wrong-thread', 'network'])(
    '%s 失败后显示失败占位并释放发送状态',
    async (kind) => {
      if (kind === 'http') fetchMock.mockResolvedValueOnce(new Response('', { status: 500 }))
      if (kind === 'business')
        fetchMock.mockResolvedValueOnce(
          new Response(JSON.stringify({ code: 20000, message: '业务处理失败', data: null })),
        )
      if (kind === 'invalid-json') fetchMock.mockResolvedValueOnce(new Response('not json'))
      if (kind === 'invalid-data')
        fetchMock.mockResolvedValueOnce(
          new Response(JSON.stringify({ code: 0, data: { reply: 123 } })),
        )
      if (kind === 'wrong-thread') fetchMock.mockResolvedValueOnce(success('other-thread'))
      if (kind === 'network') fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
      const chat = useChatStore()
      expect(await chat.send('保留这条消息')).toBe(false)
      expect(chat.isSending).toBe(false)
      expect(chat.activeConversation?.messages).toHaveLength(2)
      expect(chat.activeConversation?.messages[0]?.blocks).toEqual([
        { type: 'paragraph', text: '保留这条消息' },
      ])
      expect(chat.activeConversation?.messages[1]?.status).toBe('error')
      expect(await chat.send('再次发送')).toBe(true)
    },
  )
})
