/** 会话 JSON 校验回归：损坏页、归属不匹配和内部事件不能进入公开消息状态。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, disposePinia, type Pinia } from 'pinia'
import { authenticate } from '@/__tests__/helpers/auth'
import { conversationHistory, listConversations, deleteConversation } from '../api'
import { A, B, info, turn, response } from './helpers'

let pinia: Pinia
const fetchMock = vi.fn<typeof fetch>()
// 每例通过真实登录准备身份，随后只注入待验证的业务响应。
beforeEach(async () => {
  pinia = createPinia()
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  await authenticate(pinia, fetchMock)
})
// 销毁认证时钟并还原网络，不允许跨用例共用响应体。
afterEach(() => {
  disposePinia(pinia)
  vi.unstubAllGlobals()
  sessionStorage.clear()
})

describe('会话响应边界', () => {
  // JSON 外壳、日期、游标和数组缺失均应拒绝，不显示虚假的空目录。
  it.each([
    null,
    { items: [], next_cursor: '' },
    { items: null, next_cursor: null },
    { items: [{ ...info(), last_message_at: 'bad-date' }], next_cursor: null },
  ])('拒绝损坏目录 %#', async (data) => {
    fetchMock.mockResolvedValue(response(data))
    await expect(listConversations(new AbortController().signal)).rejects.toThrow(/会话/)
  })

  // 跨会话、乱序轮次、缺少最终回复和内部推理都必须在历史适配边界拒绝。
  it.each([
    { conversation: info(B), items: [turn()] },
    { conversation: info(), items: [turn(2), turn(1)] },
    { conversation: info(), items: [{ ...turn(), assistant_content: null }] },
    {
      conversation: info(),
      items: [
        {
          ...turn(),
          public_events: [
            {
              event: 'reasoning_delta',
              data: { conversation_id: A, message_id: 'm', text: '内部过程' },
            },
          ],
        },
      ],
    },
  ])('拒绝无效或越界历史 %#', async (data) => {
    fetchMock.mockResolvedValue(response({ ...data, next_cursor: null }))
    await expect(conversationHistory(A, new AbortController().signal)).rejects.toThrow(
      /格式无效|归属无效|缺少最终回复|历史过程事件无效/,
    )
  })

  // HTTP 与业务错误同样保留状态，删除不能把错误返回视为已删除。
  it('保留业务错误码和不存在状态，删除成功要求 data=null', async () => {
    fetchMock
      .mockResolvedValueOnce(response(null, 404, 40401, '会话不存在'))
      .mockResolvedValueOnce(response({}, 200))
    await expect(conversationHistory(A, new AbortController().signal)).rejects.toMatchObject({
      status: 404,
      code: 40401,
    })
    await expect(deleteConversation(A, new AbortController().signal)).rejects.toThrow(
      '删除会话响应格式无效',
    )
  })
})
