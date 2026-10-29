/** 文件目录状态测试：验证游标隔离、迟到响应、权限变化和异常恢复。 */
import { beforeEach, expect, it, vi } from 'vitest'
import { effectScope, reactive } from 'vue'
import { flushPromises } from '@vue/test-utils'
import { authenticate } from '@tests/support/vitest/auth'
import { createTestPinia } from '@tests/support/vitest/mount'
import { deferredResponse, response } from '@tests/support/vitest/http'
import { fileEntry, fileSpace } from '@tests/support/data/files'
import { useAuthStore } from '@/features/auth/store'
import { useFileDirectory } from '../useFileDirectory'

const fetchMock = vi.fn<typeof fetch>()
// 每例使用独立身份与请求队列。
beforeEach(async () => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  await authenticate(createTestPinia(), fetchMock)
})

/** 为当前父目录生成合法分页，按需覆盖条目和游标。 */
function directory(parentId: string | null, ids = ['one'], cursor: string | null = null) {
  return response({
    space: fileSpace(),
    parent_id: parentId,
    breadcrumbs: parentId ? [{ id: parentId, name: '目录' }] : [],
    items: ids.map((id) => fileEntry({ id, parent_id: parentId })),
    next_cursor: cursor,
  })
}

it('切换目录取消旧请求，迟到响应不覆盖新目录', async () => {
  const old = deferredResponse()
  fetchMock.mockReturnValueOnce(old.promise).mockResolvedValueOnce(directory('folder', ['new']))
  const target = reactive({ spaceId: 'space-personal', parentId: null as string | null })
  const scope = effectScope()
  const state = scope.run(() => useFileDirectory(() => target))!
  target.parentId = 'folder'
  await flushPromises()
  expect(fetchMock.mock.calls[0]![1]?.signal?.aborted).toBe(true)
  expect(state.entries.value[0]?.id).toBe('new')
  old.resolve(directory(null, ['old']))
  await flushPromises()
  expect(state.entries.value[0]?.id).toBe('new')
  scope.stop()
  expect(fetchMock.mock.calls[1]![1]?.signal?.aborted).toBe(true)
})

it('实时分页去重，无效游标从首页恢复，换目标不用旧游标', async () => {
  fetchMock.mockResolvedValueOnce(directory(null, ['one'], 'cursor-1'))
  const target = reactive({ spaceId: 'space-personal', parentId: null as string | null })
  const scope = effectScope()
  const state = scope.run(() => useFileDirectory(() => target))!
  await flushPromises()
  fetchMock.mockResolvedValueOnce(directory(null, ['one', 'two'], 'cursor-2'))
  await state.reload(true)
  expect(state.entries.value.map((row) => row.id)).toEqual(['one', 'two'])
  fetchMock
    .mockResolvedValueOnce(response(null, 422, 42200, '游标无效'))
    .mockResolvedValueOnce(directory(null, ['fresh']))
  await state.reload(true)
  expect(state.entries.value[0]?.id).toBe('fresh')
  expect(fetchMock.mock.calls.at(-1)![0]).not.toContain('cursor=')
  fetchMock.mockResolvedValueOnce(directory('folder'))
  target.parentId = 'folder'
  await flushPromises()
  expect(fetchMock.mock.calls.at(-1)![0]).not.toContain('cursor=')
  scope.stop()
})

it('目录不可见立即清空内容，身份范围变化清空旧空间和游标再读取', async () => {
  fetchMock.mockResolvedValueOnce(directory(null))
  const scope = effectScope()
  const state = scope.run(() =>
    useFileDirectory(() => ({ spaceId: 'space-personal', parentId: null })),
  )!
  await flushPromises()
  fetchMock.mockResolvedValueOnce(response(null, 404, 40406, '空间不可见'))
  await state.reload()
  expect(state.space.value).toBeNull()
  expect(state.entries.value).toEqual([])
  expect(state.error.value).toBe('空间不可见')
  fetchMock
    .mockResolvedValueOnce(response({ items: [], next_cursor: null }))
    .mockResolvedValueOnce(directory(null))
  useAuthStore().user!.department = { id: 'new-dept', name: '新部门' }
  await flushPromises()
  expect(state.spaces.value).toEqual([])
  expect(state.spaceCursor.value).toBeNull()
  scope.stop()
})

it('空间分页去重，分页出错保留原列表，失效游标恢复首页', async () => {
  const scope = effectScope()
  const state = scope.run(() => useFileDirectory(() => ({ spaceId: '', parentId: null })))!
  const personal = fileSpace()
  const global = fileSpace({ id: 'global', kind: 'global', owner_id: null })
  fetchMock.mockResolvedValueOnce(response({ items: [personal], next_cursor: 'next' }))
  await state.loadSpaces()
  fetchMock.mockResolvedValueOnce(response(null, 500, 50004, '服务不可用'))
  await state.loadSpaces(true)
  expect(state.spaces.value).toEqual([personal])
  expect(state.spacesError.value).toBe('服务不可用')
  fetchMock.mockResolvedValueOnce(response({ items: [personal, global], next_cursor: 'last' }))
  await state.loadSpaces(true)
  expect(state.spaces.value.map((item) => item.id)).toEqual([personal.id, global.id])
  fetchMock
    .mockResolvedValueOnce(response(null, 422, 42200, '游标无效'))
    .mockResolvedValueOnce(response({ items: [global], next_cursor: null }))
  await state.loadSpaces(true)
  expect(state.spaces.value).toEqual([global])
  expect(fetchMock.mock.calls.at(-1)![0]).not.toContain('cursor=')
  scope.stop()
})
