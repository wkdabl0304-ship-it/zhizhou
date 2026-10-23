/** 会话竞争与清理：控制真实接口适配的响应时序，验证迟到数据不会恢复已删除状态。 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useChatStore } from '../../store'
import { createTestPinia, disposeTestPinia } from '@tests/support/vitest/mount'
import { authenticate } from '@tests/support/vitest/auth'
import { response, deferredResponse } from '@tests/support/vitest/http'
import { A, info, turn } from '@tests/support/data/chat'

const fetchMock = vi.fn<typeof fetch>()
// 每例建立独立身份；只推进可控 HTTP 响应，不使用任意等待时间。
beforeEach(async () => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  await authenticate(createTestPinia(), fetchMock)
})

describe('请求生命周期', () => {
  it('删除期间取消历史读取，迟到历史不能恢复目录或当前会话', async () => {
    fetchMock.mockResolvedValueOnce(response({ items: [info()], next_cursor: null }))
    const chat = useChatStore()
    await chat.loadConversations()
    const history = deferredResponse()
    fetchMock.mockReturnValueOnce(history.promise).mockResolvedValueOnce(response(null))
    const selecting = chat.select(A)
    const signal = fetchMock.mock.calls[1]![1]!.signal!
    await chat.remove(A)
    expect(signal.aborted).toBe(true)
    history.resolve(response({ conversation: info(), items: [turn()], next_cursor: null }))
    await selecting
    expect(chat.conversations).toEqual([])
    expect(chat.activeId).toBeNull()
  })

  it('状态容器销毁取消在途目录，迟到响应仍不写回缓存', async () => {
    const directory = deferredResponse()
    fetchMock.mockReturnValueOnce(directory.promise)
    const chat = useChatStore()
    const loading = chat.loadConversations()
    const signal = fetchMock.mock.calls[0]![1]!.signal!
    disposeTestPinia()
    expect(signal.aborted).toBe(true)
    directory.resolve(response({ items: [info()], next_cursor: null }))
    await loading
    expect(chat.conversations).toEqual([])
    expect(chat.listing).toBe(false)
  })

  it('历史游标未推进时保留已有消息和重试入口，刷新成功后清除错误', async () => {
    fetchMock
      .mockResolvedValueOnce(response({ items: [info()], next_cursor: null }))
      .mockResolvedValueOnce(
        response({ conversation: info(), items: [turn(2)], next_cursor: 'older' }),
      )
      .mockResolvedValueOnce(
        response({ conversation: info(), items: [turn(1)], next_cursor: 'older' }),
      )
      .mockResolvedValueOnce(
        response({ conversation: info(), items: [turn(1), turn(2)], next_cursor: null }),
      )
    const chat = useChatStore()
    await chat.loadConversations()
    await chat.select(A)
    await chat.loadEarlier()
    expect(chat.activeConversation).toMatchObject({
      nextCursor: 'older',
      loading: false,
      historyError: '历史游标未推进，请刷新会话',
    })
    expect(chat.activeConversation!.messages).toHaveLength(2)
    await chat.refreshHistory()
    expect(chat.activeConversation).toMatchObject({
      nextCursor: null,
      historyError: '',
      loading: false,
    })
    expect(chat.activeConversation!.messages).toHaveLength(4)
  })
})
