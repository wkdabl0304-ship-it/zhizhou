/** 上传生命周期测试：按钮与拖放共用规则，覆盖目标冻结、部分失败、中止和迟到响应。 */
import { effectScope, reactive, nextTick } from 'vue'
import { beforeEach, expect, it, vi } from 'vitest'
import { authenticate } from '@tests/support/vitest/auth'
import { createTestPinia } from '@tests/support/vitest/mount'
import { deferredResponse, response } from '@tests/support/vitest/http'
import { fileEntry, fileSpace } from '@tests/support/data/files'
import { useFileUpload } from '../useFileUpload'
import type { FileSpace } from '../types'

const fetchMock = vi.fn<typeof fetch>()
// 每例使用独立身份；状态作用域在例内主动停止，以验证取消生命周期。
beforeEach(async () => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  await authenticate(createTestPinia(), fetchMock)
})

/** 挂载独立上传状态，测试能够改变目录但不直接操作请求内部变量。 */
function setup() {
  const target = reactive({
    space: fileSpace({ max_file_size_bytes: 4 }) as FileSpace | null,
    parentId: null as string | null,
    key: 'root',
  })
  const uploaded = vi.fn<() => void>()
  const scope = effectScope()
  const state = scope.run(() => useFileUpload(() => target, uploaded))!
  return { target, uploaded, scope, state }
}

it('允许空文件，超限不请求，部分失败不自动重试并重新核对目录', async () => {
  const { state, uploaded, scope } = setup()
  fetchMock
    .mockResolvedValueOnce(response(fileEntry({ size_bytes: 0 })))
    .mockRejectedValueOnce(new Error('断开'))
  await state.upload([
    new File([], '空.txt'),
    new File(['12345'], '太大.txt'),
    new File(['12'], '失败.txt'),
  ])
  expect(fetchMock).toHaveBeenCalledTimes(2)
  expect(state.failures.value.join(' ')).toContain('太大.txt：超过当前单文件上限')
  expect(state.failures.value.join(' ')).toContain('失败.txt：网络连接失败')
  expect(uploaded).toHaveBeenCalledOnce()
  expect(state.busy.value).toBe(false)
  scope.stop()
})

it('明确的文件夹目标用于全部文件，目录同步的临时空状态不会取消传输', async () => {
  const { state, target, scope } = setup()
  const pending = deferredResponse()
  fetchMock.mockReturnValueOnce(pending.promise).mockResolvedValueOnce(response(fileEntry()))
  const task = state.upload([new File(['1'], '一.txt'), new File(['2'], '二.txt')], {
    space: fileSpace(),
    parentId: 'folder',
  })
  target.space = null
  await nextTick()
  expect(fetchMock.mock.calls[0]![1]?.signal?.aborted).toBe(false)
  target.space = fileSpace()
  await nextTick()
  pending.resolve(response(fileEntry()))
  await task
  expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
    '/api/files/spaces/space-personal/files?parent_id=folder',
    '/api/files/spaces/space-personal/files?parent_id=folder',
  ])
  scope.stop()
})

it('中止只显示一次说明，停止后续文件并核对可能已发布的结果', async () => {
  const { state, uploaded, scope } = setup()
  const pending = deferredResponse()
  fetchMock.mockReturnValueOnce(pending.promise)
  const task = state.upload([new File(['1'], '一.txt'), new File(['2'], '二.txt')])
  await state.upload([new File(['3'], '重复选择.txt')])
  expect(fetchMock).toHaveBeenCalledOnce()
  state.cancel()
  state.cancel()
  expect(fetchMock.mock.calls[0]![1]?.signal?.aborted).toBe(true)
  pending.resolve(response(fileEntry()))
  await task
  expect(fetchMock).toHaveBeenCalledOnce()
  expect(state.failures.value).toHaveLength(1)
  expect(uploaded).toHaveBeenCalledOnce()
  scope.stop()
})

it('切换目录、撤销上传能力和卸载均取消旧请求，迟到结果不污染新位置', async () => {
  const { state, target, uploaded, scope } = setup()
  const old = deferredResponse()
  fetchMock.mockReturnValueOnce(old.promise)
  const task = state.upload([new File(['1'], '旧.txt')])
  target.key = 'another'
  await nextTick()
  expect(fetchMock.mock.calls[0]![1]?.signal?.aborted).toBe(true)
  old.resolve(response(fileEntry()))
  await task
  expect(uploaded).not.toHaveBeenCalled()
  expect(state.failures.value).toEqual([])
  const later = deferredResponse()
  fetchMock.mockReturnValueOnce(later.promise)
  const next = state.upload([new File(['2'], '新.txt')])
  target.space = fileSpace({ capabilities: ['read'] })
  await nextTick()
  expect(fetchMock.mock.calls[1]![1]?.signal?.aborted).toBe(true)
  scope.stop()
  later.resolve(response(fileEntry()))
  await next
  expect(uploaded).not.toHaveBeenCalled()
})
