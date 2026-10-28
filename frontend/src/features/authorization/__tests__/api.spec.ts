/** 组织接口契约测试：验证路径、筛选、响应白名单与写入输入，全部使用独立 HTTP 替身。 */
import { beforeEach, expect, it, vi } from 'vitest'
import { createTestPinia } from '@tests/support/vitest/mount'
import { authenticate } from '@tests/support/vitest/auth'
import { response } from '@tests/support/vitest/http'
import { authorizationData } from '@tests/support/data/authorization'
import { decodeDepartment, decodeMember, decodeUser, execute, list } from '../api'
import type { ManagementAction } from '../types'

const fetchMock = vi.fn<typeof fetch>()
beforeEach(async () => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  await authenticate(createTestPinia(), fetchMock)
})

it('游标与筛选按原值编码，明确 false 筛选不会丢失', async () => {
  const { managedUser } = authorizationData()
  fetchMock.mockResolvedValue(response({ items: [managedUser], next_cursor: 'opaque/+' }))
  const signal = new AbortController().signal
  expect(
    await list(
      'users',
      { search: 'a_b%', is_active: false, cursor: 'opaque/+', unassigned: true },
      decodeUser,
      signal,
    ),
  ).toEqual({ items: [managedUser], next_cursor: 'opaque/+' })
  const [url, options] = fetchMock.mock.calls[0]!
  expect(String(url)).toBe(
    '/api/users?limit=20&search=a_b%25&is_active=false&cursor=opaque%2F%2B&unassigned=true',
  )
  expect(options?.signal).toBe(signal)
  expect(new Headers(options?.headers).get('Authorization')).toBe('Bearer test-access-token')
})

it('拒绝不完整的部门、成员、账号及分页结构', async () => {
  const { department, member, managedUser } = authorizationData()
  expect(() => decodeDepartment({ ...department, created_at: 'bad-date' })).toThrow('响应格式无效')
  expect(() => decodeMember({ ...member, is_active: 'true' })).toThrow('响应格式无效')
  expect(() => decodeUser({ ...managedUser, department: undefined })).toThrow('响应格式无效')
  expect(() => decodeUser({ ...managedUser, roles: [2] })).toThrow('响应格式无效')
  fetchMock.mockResolvedValue(response({ items: [department], next_cursor: 1 }))
  await expect(
    list('departments', {}, decodeDepartment, new AbortController().signal),
  ).rejects.toThrow('响应格式无效')
})

it('部门创建、改名和加入成员只发送接口支持的规范化字段', async () => {
  const { department, member } = authorizationData(),
    signal = new AbortController().signal
  fetchMock
    .mockResolvedValueOnce(response(department))
    .mockResolvedValueOnce(response(department))
    .mockResolvedValueOnce(response(member))
  await execute({ kind: 'create-department' }, ' 山海研发部 ', signal)
  await execute({ kind: 'rename-department', department }, ' 新名称 ', signal)
  await execute({ kind: 'add-member', department }, ' Team_Member ', signal)
  expect(
    fetchMock.mock.calls.map(([path, options]) => [
      path,
      options?.method,
      JSON.parse(String(options?.body)),
    ]),
  ).toEqual([
    ['/api/departments', 'POST', { name: '山海研发部' }],
    [`/api/departments/${department.id}`, 'PATCH', { name: '新名称' }],
    [`/api/departments/${department.id}/members`, 'POST', { username: 'team_member' }],
  ])
})

it('启停使用明确布尔值，重置密码保留空格且不创建额外字段', async () => {
  const { managedUser: user } = authorizationData(),
    signal = new AbortController().signal
  fetchMock
    .mockResolvedValueOnce(response(user))
    .mockResolvedValueOnce(response(user))
    .mockResolvedValueOnce(response(null))
  await execute({ kind: 'disable-user', user }, '', signal)
  await execute({ kind: 'enable-user', user }, '', signal)
  await execute({ kind: 'reset-password', user }, ' password with spaces ', signal)
  expect(fetchMock.mock.calls.map(([, options]) => JSON.parse(String(options?.body)))).toEqual([
    { is_active: false },
    { is_active: true },
    { password: ' password with spaces ' },
  ])
})

it.each([
  ['delete-department', 'DELETE', 'departments/d%2Fid'],
  ['remove-member', 'DELETE', 'departments/d%2Fid/members/m%2Fid'],
  ['assign-department-admin', 'PUT', 'departments/d%2Fid/administrators/m%2Fid'],
  ['revoke-department-admin', 'DELETE', 'departments/d%2Fid/administrators/m%2Fid'],
  ['assign-super-admin', 'PUT', 'users/u%2Fid/super-admin'],
  ['revoke-super-admin', 'DELETE', 'users/u%2Fid/super-admin'],
] as const)('%s 使用安全路径和正确方法', async (kind, method, path) => {
  const { department, member, managedUser } = authorizationData()
  const action = {
    kind,
    department: { ...department, id: 'd/id' },
    member: { ...member, id: 'm/id' },
    user: { ...managedUser, id: 'u/id' },
  } as ManagementAction
  fetchMock.mockResolvedValue(response(null))
  await execute(action, '', new AbortController().signal)
  expect(fetchMock.mock.calls[0]![0]).toBe(`/api/${path}`)
  expect(fetchMock.mock.calls[0]![1]?.method).toBe(method)
  expect(fetchMock.mock.calls[0]![1]?.body).toBeUndefined()
})
