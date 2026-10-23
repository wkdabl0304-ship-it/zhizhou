/** 聊天业务回归：验证服务端签发 ID、Bearer 续聊、并发归属、退出取消及失败保留。 */
import { createTestPinia as createPinia } from '@tests/support/vitest/mount'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { disposePinia, type Pinia } from 'pinia'
import { flushPromises } from '@vue/test-utils'
import { useChatStore } from '@/features/chat/store'
import { useAuthStore } from '@/features/auth/store'
import { authenticate } from '@tests/support/vitest/auth'
import { controlledStream, sseResponse } from '@tests/support/vitest/sse'
import { eventFrame, success } from '@tests/support/vitest/chat'

const fetchMock = vi.fn<typeof fetch>()
let pinia: Pinia
let serverSequence: number
const OTHER = '00000000-0000-4000-8000-000000000099'
// 服务器替身生成 ID，前端请求不能预先携带首次 ID；认证准备不计入聊天请求数。
beforeEach(async () => {
  pinia = createPinia()
  serverSequence = 0
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  await authenticate(pinia, fetchMock)
  fetchMock.mockImplementation(async (_url, options) => {
    const body = JSON.parse(options!.body as string) as { conversation_id?: string }
    return success(
      body.conversation_id ??
        `00000000-0000-4000-8000-${String(++serverSequence).padStart(12, '0')}`,
      '后端真实格式的回复',
      !body.conversation_id,
    )
  })
})
// 销毁请求和令牌定时器，测试不连接真实服务。
afterEach(() => {
  disposePinia(pinia)
  vi.unstubAllGlobals()
  sessionStorage.clear()
})

describe('服务端聊天会话', () => {
  // 空输入或仅点击新建都不创建后端空会话。
  it('空白与新建不发送请求、不生成业务 ID', async () => {
    const chat = useChatStore()
    chat.startNew()
    expect(await chat.send(' \n ')).toBe(false)
    expect(chat.activeId).toBeNull()
    expect(chat.conversations).toHaveLength(0)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  // 只有 start 返回的 ID 可用于后续请求，令牌随每次请求发送。
  it('首次省略 ID，收到 start 后多轮复用服务端 ID', async () => {
    const chat = useChatStore()
    expect(await chat.send('  工作计划  ')).toBe(true)
    const id = chat.activeId!
    expect(id).toBe('00000000-0000-4000-8000-000000000001')
    expect(JSON.parse(fetchMock.mock.calls[0]![1]!.body as string)).toEqual({ message: '工作计划' })
    expect(new Headers(fetchMock.mock.calls[0]![1]!.headers).get('authorization')).toBe(
      'Bearer test-access-token',
    )
    expect(await chat.send('继续')).toBe(true)
    expect(JSON.parse(fetchMock.mock.calls[1]![1]!.body as string)).toEqual({
      message: '继续',
      conversation_id: id,
    })
    expect(chat.activeConversation?.messages).toHaveLength(4)
    expect(chat.activeConversation?.messages[3]?.status).toBe('complete')
    chat.startNew()
    await chat.send('另一个话题')
    expect(chat.activeId).not.toBe(id)
    await chat.select(id)
    expect(chat.activeId).toBe(id)
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  // 每会话只允许一轮，但用户可以切到另一会话；迟到的旧 start 不应抢回当前选择。
  it('阻止同会话并发，切换后旧流只写回原会话', async () => {
    const stream = controlledStream()
    fetchMock.mockResolvedValueOnce(stream.response)
    const chat = useChatStore()
    const pending = chat.send('慢任务')
    expect(await chat.send('重复任务')).toBe(false)
    chat.startNew()
    await chat.send('新任务')
    const newer = chat.activeId
    stream.push(
      eventFrame('start', { conversation_id: OTHER }) +
        eventFrame('delta', { conversation_id: OTHER, message_id: 'old', text: '旧进度' }) +
        eventFrame('done', { conversation_id: OTHER, message_id: 'final', reply: '旧回答' }),
    )
    expect(await pending).toBe(true)
    expect(chat.activeId).toBe(newer)
    expect(chat.activeConversation?.messages[1]?.blocks).not.toContainEqual({
      type: 'paragraph',
      text: '旧回答',
    })
    await chat.select(OTHER)
    expect(chat.activeConversation?.messages[1]?.blocks).toEqual([
      { type: 'paragraph', text: '旧回答' },
    ])
    expect(stream.isCancelled()).toBe(true)
  })

  // 账号退出必须取消等待中的流，而非仅清空 DOM；之后旧响应不能恢复目录。
  it('退出账号清空状态并取消流式读取', async () => {
    const stream = controlledStream()
    fetchMock.mockResolvedValueOnce(stream.response)
    const chat = useChatStore()
    const pending = chat.send('旧账号任务')
    stream.push(eventFrame('start', { conversation_id: OTHER }))
    await flushPromises()
    const signal = fetchMock.mock.calls[0]![1]!.signal
    useAuthStore().logout()
    expect(await pending).toBe(false)
    expect(signal?.aborted).toBe(true)
    expect(stream.isCancelled()).toBe(true)
    expect(chat.conversations).toHaveLength(0)
    expect(chat.activeId).toBeNull()
  })

  // 无法确认完成时保留用户消息和可见正文；禁止隐式重放可能已落库的用户输入。
  it.each(['error', 'eof', 'disconnect'])('%s 中断保留正文，不自动重试', async (kind) => {
    const stream = controlledStream()
    fetchMock.mockResolvedValueOnce(stream.response)
    const chat = useChatStore()
    const pending = chat.send('请继续')
    stream.push(
      eventFrame('start', { conversation_id: OTHER }) +
        eventFrame('delta', { conversation_id: OTHER, message_id: 'partial', text: '部分内容' }),
    )
    await flushPromises()
    expect(chat.activeConversation?.messages[1]?.status).toBe('streaming')
    if (kind === 'error') stream.push(eventFrame('error', null, 50000))
    if (kind === 'eof') stream.close()
    if (kind === 'disconnect') stream.fail()
    expect(await pending).toBe(false)
    expect(chat.activeConversation?.messages[1]).toMatchObject({
      status: 'error',
      blocks: [{ type: 'paragraph', text: '部分内容' }],
    })
    expect(chat.isSending).toBe(false)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  // 首次请求未收到 start 时只留下本地未完成展示，下一次显式发送仍不能带本地 draft 键。
  it('首轮失败后重试仍不发送本地展示键', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('offline'))
    const chat = useChatStore()
    expect(await chat.send('失败任务')).toBe(false)
    expect(chat.activeConversation?.persisted).toBe(false)
    expect(await chat.send('明确重试')).toBe(true)
    expect(JSON.parse(fetchMock.mock.calls[1]![1]!.body as string)).toEqual({ message: '明确重试' })
    expect(chat.activeConversation?.persisted).toBe(true)
  })

  // done 的权威最终正文替换部分增量，进度和工具时间线由原有专用回归继续覆盖。
  it('最终回答替换增量正文并结束等待', async () => {
    fetchMock.mockResolvedValueOnce(
      sseResponse(
        eventFrame('start', { conversation_id: OTHER }) +
          eventFrame('delta', { conversation_id: OTHER, message_id: 'a', text: '临时内容' }) +
          eventFrame('done', { conversation_id: OTHER, message_id: 'a', reply: '最终正文' }),
      ),
    )
    const chat = useChatStore()
    expect(await chat.send('消息')).toBe(true)
    expect(chat.activeConversation?.messages[1]).toMatchObject({
      status: 'complete',
      blocks: [{ type: 'paragraph', text: '最终正文' }],
      activities: [],
    })
    expect(chat.isSending).toBe(false)
  })
})
