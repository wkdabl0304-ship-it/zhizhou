/** 游标目录生命周期测试：验证筛选与账号隔离、失败重试、游标失效及资源释放。 */
import { effectScope, ref } from 'vue'
import { flushPromises } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import { createTestPinia } from '@tests/support/vitest/mount'
import { authenticate } from '@tests/support/vitest/auth'
import { deferredResponse, response } from '@tests/support/vitest/http'
import { authorizationData } from '@tests/support/data/authorization'
import { useAuthStore } from '@/features/auth/store'
import { decodeUser } from '../api'
import { useDirectory } from '../useDirectory'
import type { Query } from '../types'

const fetchMock = vi.fn<typeof fetch>()
beforeEach(async () => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  await authenticate(createTestPinia(), fetchMock)
})

/** 在可销毁作用域创建目录，保留真实监听与异步取消。 */
function directory() {
  const scope = effectScope(),
    path = ref('users'),
    query = ref<Query>({ search: 'first' })
  const state = scope.run(() => useDirectory(path, query, decodeUser))!
  return { scope, path, query, ...state }
}

it('筛选变化清空旧游标并取消请求，迟到结果不能覆盖新目录', async () => {
  const pending = deferredResponse(),
    { managedUser } = authorizationData()
  fetchMock
    .mockReturnValueOnce(pending.promise)
    .mockResolvedValue(response({ items: [{ ...managedUser, id: 'new' }], next_cursor: null }))
  const state = directory(),
    signal = fetchMock.mock.calls[0]![1]?.signal
  state.query.value = { search: 'second' }
  await flushPromises()
  expect(signal?.aborted).toBe(true)
  pending.resolve(response({ items: [managedUser], next_cursor: 'old' }))
  await flushPromises()
  expect(state.items.value.map((row) => row.id)).toEqual(['new'])
  expect(fetchMock.mock.calls[1]![0]).toBe('/api/users?limit=20&search=second')
  state.scope.stop()
})

it('翻页保持筛选并去重，无效游标自动从第一页恢复', async () => {
  const { managedUser } = authorizationData()
  fetchMock
    .mockResolvedValueOnce(response({ items: [managedUser], next_cursor: 'next' }))
    .mockResolvedValueOnce(
      response({ items: [managedUser, { ...managedUser, id: 'second' }], next_cursor: 'expired' }),
    )
    .mockResolvedValueOnce(response(null, 422, 42200, '游标无效'))
    .mockResolvedValueOnce(
      response({ items: [{ ...managedUser, id: 'fresh' }], next_cursor: null }),
    )
  const state = directory()
  await flushPromises()
  await state.load(true)
  expect(state.items.value).toHaveLength(2)
  expect(fetchMock.mock.calls[1]![0]).toBe('/api/users?limit=20&search=first&cursor=next')
  await state.load(true)
  expect(state.items.value.map((row) => row.id)).toEqual(['fresh'])
  expect(fetchMock.mock.calls[3]![0]).toBe('/api/users?limit=20&search=first')
  state.scope.stop()
})

it('失败保留重试入口，退出账号后取消并清空目录', async () => {
  const { managedUser } = authorizationData()
  fetchMock
    .mockResolvedValueOnce(response(null, 503, 50000, '服务暂不可用'))
    .mockResolvedValueOnce(response({ items: [managedUser], next_cursor: null }))
  const state = directory()
  await flushPromises()
  expect(state.error.value).toBe('服务暂不可用')
  await state.load()
  expect(state.error.value).toBe('')
  expect(state.items.value).toHaveLength(1)
  useAuthStore().logout()
  await flushPromises()
  expect(state.items.value).toEqual([])
  state.scope.stop()
})
