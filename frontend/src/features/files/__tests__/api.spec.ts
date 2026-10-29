/** 文件 API 契约测试：验证认证、multipart、并发版本、下载完整性及响应边界。 */
import { beforeEach, expect, it, vi } from 'vitest'
import { authenticate } from '@tests/support/vitest/auth'
import { createTestPinia } from '@tests/support/vitest/mount'
import { response } from '@tests/support/vitest/http'
import { fileEntry, filePolicy, fileSpace } from '@tests/support/data/files'
import * as api from '../api'
import { formatSize, validateName } from '../format'

const fetchMock = vi.fn<typeof fetch>()
const signal = new AbortController().signal

// 通过真实认证 store 建立身份，网络响应保持可控。
beforeEach(async () => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  await authenticate(createTestPinia(), fetchMock)
})

it('上传仅发送一个 file 字段并保留服务端另存名称，不自动重试', async () => {
  const saved = fileEntry({ name: '山海笔记 (1).txt' })
  fetchMock.mockResolvedValueOnce(response(saved))
  expect(
    await api.uploadFile('space-personal', 'parent', new File(['山海'], '山海笔记.txt'), signal),
  ).toEqual(saved)
  const [url, init] = fetchMock.mock.calls[0]!
  expect(url).toContain('?parent_id=parent')
  expect(init?.headers).toEqual({ authorization: 'Bearer test-access-token' })
  expect([...(init!.body as FormData).keys()]).toEqual(['file'])
  fetchMock.mockRejectedValueOnce(new Error('断网'))
  await expect(
    api.uploadFile('space-personal', null, new File([], '空.txt'), signal),
  ).rejects.toThrow('网络连接失败')
  expect(fetchMock).toHaveBeenCalledTimes(2)
})

it('改名及删除携带读取时版本，业务冲突不会转为成功', async () => {
  const entry = fileEntry({ version: 7 })
  fetchMock.mockResolvedValueOnce(response(fileEntry({ version: 8, name: '新名.txt' })))
  await api.renameEntry(entry, '新名.txt', signal)
  expect(JSON.parse(fetchMock.mock.calls[0]![1]!.body as string)).toEqual({
    name: '新名.txt',
    version: 7,
  })
  fetchMock.mockResolvedValueOnce(response(null, 409, 40910, '版本冲突'))
  await expect(api.deleteEntry(entry, signal)).rejects.toMatchObject({ code: 40910 })
  expect(fetchMock.mock.calls[1]![0]).toContain('?version=7')
})

it('目录分页保留父目录与游标，并拒绝其他目录条目和损坏对象', async () => {
  const space = fileSpace()
  fetchMock.mockResolvedValueOnce(
    response({
      space,
      parent_id: 'folder',
      breadcrumbs: [{ id: 'folder', name: '目录' }],
      items: [fileEntry({ parent_id: 'folder' })],
      next_cursor: null,
    }),
  )
  expect((await api.listEntries(space.id, 'folder', signal, 'a+b')).items).toHaveLength(1)
  expect(String(fetchMock.mock.calls[0]![0])).toContain('cursor=a%2Bb')
  fetchMock.mockResolvedValueOnce(
    response({
      space,
      parent_id: 'folder',
      breadcrumbs: [],
      items: [fileEntry()],
      next_cursor: null,
    }),
  )
  await expect(api.listEntries(space.id, 'folder', signal)).rejects.toThrow('响应格式无效')
  expect(() => api.decodeEntry(fileEntry({ version: 0 }))).toThrow('响应格式无效')
  expect(() => api.decodeEntry(fileEntry({ kind: 'folder' }))).toThrow('响应格式无效')
  expect(() => api.decodeSpace(fileSpace({ capabilities: ['execute' as never] }))).toThrow(
    '响应格式无效',
  )
})

it('上传策略以范围映射 URL，个人策略不带用户 ID，并携带策略版本', async () => {
  const space = fileSpace()
  fetchMock.mockResolvedValueOnce(response(filePolicy(space)))
  await api.uploadLimit(space, signal, { max_file_size_bytes: 1024, version: 3 })
  expect(fetchMock.mock.calls[0]![0]).toBe('/api/files/upload-limits/personal')
  expect(JSON.parse(fetchMock.mock.calls[0]![1]!.body as string)).toEqual({
    max_file_size_bytes: 1024,
    version: 3,
  })
  const department = fileSpace({ kind: 'department', department_id: 'dept', owner_id: null })
  fetchMock.mockResolvedValueOnce(response(filePolicy(department)))
  await api.uploadLimit(department, signal)
  expect(fetchMock.mock.calls[1]![0]).toBe('/api/files/upload-limits/departments/dept')
})

it('下载检查完整字节、使用附件名称并释放对象 URL，错误响应不会成为附件', async () => {
  const create = vi.fn<typeof URL.createObjectURL>(() => 'blob:download')
  const revoke = vi.fn<typeof URL.revokeObjectURL>()
  // 独立子类只替换本例对象 URL 能力，不修改原始构造器而污染后续用例。
  vi.stubGlobal(
    'URL',
    class extends URL {
      static createObjectURL = create
      static revokeObjectURL = revoke
    },
  )
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  fetchMock.mockResolvedValueOnce(new Response('123456'))
  vi.useFakeTimers()
  try {
    await api.downloadFile(fileEntry(), signal)
    expect(create).toHaveBeenCalledOnce()
    expect((click.mock.instances[0] as HTMLAnchorElement).download).toBe('山海笔记.txt')
    await vi.advanceTimersByTimeAsync(1000)
    expect(revoke).toHaveBeenCalledWith('blob:download')
  } finally {
    vi.useRealTimers()
    click.mockRestore()
  }
  fetchMock.mockResolvedValueOnce(new Response('12'))
  await expect(api.downloadFile(fileEntry(), signal)).rejects.toThrow('不完整')
  fetchMock.mockResolvedValueOnce(response(null, 500, 50004, '原件缺失'))
  await expect(api.downloadFile(fileEntry(), signal)).rejects.toThrow('原件缺失')
  expect(create).toHaveBeenCalledOnce()
})

it('容量与名称验证区分空文件、目录及非法路径，按 Unicode 字符计数', () => {
  expect(formatSize(0)).toBe('0 B')
  expect(formatSize(null)).toBe('—')
  expect(formatSize(104857600)).toBe('100 MB')
  for (const value of ['..', '.', 'a/b', 'a\\b', 'a\u0000b', ' '])
    expect(validateName(value)).not.toBe('')
  expect(validateName('舟'.repeat(255))).toBe('')
  expect(validateName('舟'.repeat(256))).not.toBe('')
})
