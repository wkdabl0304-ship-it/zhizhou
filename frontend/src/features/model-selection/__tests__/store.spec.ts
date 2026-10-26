/** 允许范围状态回归：验证最近读取优先、退出清理和错误不冒充空配置。 */
import { beforeEach, expect, it, vi } from 'vitest'
import { createTestPinia } from '@tests/support/vitest/mount'
import { authenticate } from '@tests/support/vitest/auth'
import { deferredResponse, response } from '@tests/support/vitest/http'
import { modelOptionsData } from '@tests/support/data/model-selection'
import { useAuthStore } from '@/features/auth/store'
import { useModelSelectionStore } from '../store'
const fetchMock = vi.fn<typeof fetch>()
beforeEach(async () => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  await authenticate(createTestPinia(), fetchMock)
})
it('旧请求取消后迟到不能覆盖最新范围，退出清理全部状态', async () => {
  const store = useModelSelectionStore(),
    old = deferredResponse(),
    data = modelOptionsData()
  fetchMock.mockReturnValueOnce(old.promise)
  const pending = store.load(),
    signal = fetchMock.mock.lastCall?.[1]?.signal
  fetchMock.mockResolvedValueOnce(response({ providers: [], default_selection: null }))
  await store.load()
  expect(signal?.aborted).toBe(true)
  old.resolve(response(data))
  await pending
  expect(store.options?.providers).toEqual([])
  useAuthStore().logout()
  expect(store.options).toBeNull()
})
it('读取失败保留旧范围并明确报错，成功重试后清除错误', async () => {
  const store = useModelSelectionStore(),
    data = modelOptionsData()
  fetchMock.mockResolvedValueOnce(response(data))
  await store.load()
  fetchMock.mockResolvedValueOnce(response(null, 500, 50000, '读取失败'))
  await store.load()
  expect(store.error).toBe('读取失败')
  expect(store.models).toHaveLength(1)
  fetchMock.mockResolvedValueOnce(response(data))
  await store.load()
  expect(store.error).toBe('')
})
