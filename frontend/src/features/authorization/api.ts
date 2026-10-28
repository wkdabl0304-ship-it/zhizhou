/** 组织管理 HTTP 边界：复用当前凭据，校验响应后才把公开资料交给页面。 */
import { ApiError, authenticatedFetch, readEnvelope } from '@/features/auth/authenticated'
import type { Department, ManagedUser, ManagementAction, Member, Page, Query } from './types'

/** 拒绝不完整的管理响应，避免错误目标进入后续操作。 */
function requireValue(value: unknown): asserts value {
  if (!value) throw new ApiError('组织管理响应格式无效，请稍后重试')
}

/** 取得待验证的 JSON 对象。 */
function object(value: unknown): Record<string, unknown> {
  requireValue(value && typeof value === 'object' && !Array.isArray(value))
  return value as Record<string, unknown>
}

/** 检查非空公开文本。 */
function text(value: unknown): value is string {
  return typeof value === 'string' && !!value.trim()
}

/** 校验部门摘要。 */
function brief(value: unknown): void {
  const row = object(value)
  requireValue(text(row.id) && text(row.name))
}

/** 校验公开时间戳，不把无效日期传给显示组件。 */
function timestamps(row: Record<string, unknown>): void {
  requireValue(
    text(row.created_at) &&
      Number.isFinite(Date.parse(row.created_at)) &&
      text(row.updated_at) &&
      Number.isFinite(Date.parse(row.updated_at)),
  )
}

/** 校验部门资料。 */
export function decodeDepartment(value: unknown): Department {
  brief(value)
  timestamps(object(value))
  return value as Department
}

/** 校验部门内成员资料，不要求服务端公开全局角色。 */
export function decodeMember(value: unknown): Member {
  const row = object(value)
  requireValue(
    text(row.id) &&
      text(row.username) &&
      typeof row.is_active === 'boolean' &&
      Array.isArray(row.roles) &&
      row.roles.every(text),
  )
  return value as Member
}

/** 校验全站账号管理资料。 */
export function decodeUser(value: unknown): ManagedUser {
  decodeMember(value)
  const row = object(value)
  if (row.department !== null) brief(row.department)
  timestamps(row)
  return value as ManagedUser
}

/** 发出带身份的 JSON 请求，不持久化表单和密码。 */
async function request(
  path: string,
  signal: AbortSignal,
  method = 'GET',
  body?: object,
): Promise<unknown> {
  return readEnvelope(
    await authenticatedFetch(`/api/${path}`, {
      method,
      signal,
      headers: {
        Accept: 'application/json',
        ...(body ? { 'Content-Type': 'application/json' } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    }),
  )
}

/** 读取受授权范围与筛选约束的游标分页，下一页保持查询条件不变。 */
export async function list<T>(
  path: string,
  query: Query,
  decode: (value: unknown) => T,
  signal: AbortSignal,
): Promise<Page<T>> {
  const params = new URLSearchParams({ limit: '20' })
  for (const [key, value] of Object.entries(query))
    if (value !== undefined && value !== '') params.set(key, String(value))
  const row = object(await request(`${path}?${params}`, signal))
  requireValue(Array.isArray(row.items) && (row.next_cursor === null || text(row.next_cursor)))
  return {
    items: (row.items as unknown[]).map(decode),
    next_cursor: row.next_cursor as string | null,
  }
}

/** 按冻结的目标执行单次管理操作；空密码不会被去空白或写入共享状态。 */
export async function execute(
  action: ManagementAction,
  input: string,
  signal: AbortSignal,
): Promise<void> {
  const department =
    'department' in action ? `departments/${encodeURIComponent(action.department.id)}` : ''
  const user = 'user' in action ? `users/${encodeURIComponent(action.user.id)}` : ''
  const member = 'member' in action ? encodeURIComponent(action.member.id) : ''
  switch (action.kind) {
    case 'create-department':
      decodeDepartment(await request('departments', signal, 'POST', { name: input.trim() }))
      return
    case 'rename-department':
      decodeDepartment(await request(department, signal, 'PATCH', { name: input.trim() }))
      return
    case 'add-member':
      decodeMember(
        await request(`${department}/members`, signal, 'POST', {
          username: input.trim().toLowerCase(),
        }),
      )
      return
    case 'enable-user':
    case 'disable-user':
      decodeUser(
        await request(`${user}/active`, signal, 'PUT', {
          is_active: action.kind === 'enable-user',
        }),
      )
      return
    default: {
      const targets = {
        'delete-department': [department, 'DELETE'],
        'remove-member': [`${department}/members/${member}`, 'DELETE'],
        'assign-department-admin': [`${department}/administrators/${member}`, 'PUT'],
        'revoke-department-admin': [`${department}/administrators/${member}`, 'DELETE'],
        'reset-password': [`${user}/password`, 'PUT'],
        'assign-super-admin': [`${user}/super-admin`, 'PUT'],
        'revoke-super-admin': [`${user}/super-admin`, 'DELETE'],
      } as const
      const [path, method] = targets[action.kind]
      requireValue(
        (await request(
          path,
          signal,
          method,
          action.kind === 'reset-password' ? { password: input } : undefined,
        )) === null,
      )
    }
  }
}
