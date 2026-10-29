/** 资料库 HTTP 边界：复用认证请求，验证公开响应并负责附件下载的资源释放。 */
import { ApiError, authenticatedFetch, readEnvelope } from '@/features/auth/authenticated'
import type {
  Breadcrumb,
  DirectoryPage,
  FileEntry,
  FilePage,
  FileSpace,
  UploadLimit,
} from './types'

/** 拒绝缺失或不合法的公开字段，避免生成错误的后续写入目标。 */
function requireValue(value: unknown): asserts value {
  if (!value) throw new ApiError('文件服务响应格式无效，请稍后重试')
}

/** 取得可校验的公开对象。 */
function object(value: unknown): Record<string, unknown> {
  requireValue(value && typeof value === 'object' && !Array.isArray(value))
  return value as Record<string, unknown>
}

/** 检查公开标识或非空文字。 */
function text(value: unknown): value is string {
  return typeof value === 'string' && !!value.trim()
}

/** 判断接口整数是否处于允许范围，拒绝精度丢失。 */
function integer(value: unknown, min = 1, max = Number.MAX_SAFE_INTEGER): boolean {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= min && value <= max
}

/** 检查可空标识。 */
function nullableId(value: unknown): boolean {
  return value === null || text(value)
}

/** 校验空间能力和归属，未知能力不进入按钮权限判断。 */
export function decodeSpace(value: unknown): FileSpace {
  const row = object(value)
  requireValue(
    text(row.id) &&
      text(row.name) &&
      ['global', 'department', 'personal'].includes(String(row.kind)),
  )
  requireValue(
    nullableId(row.department_id) &&
      nullableId(row.owner_id) &&
      integer(row.max_file_size_bytes, 1, 1099511627776),
  )
  requireValue(
    Array.isArray(row.capabilities) &&
      row.capabilities.every(
        // 服务端是能力来源，前端只认可契约中的四种操作。
        (item) => ['read', 'upload', 'update', 'delete'].includes(item),
      ),
  )
  requireValue(
    (row.kind === 'department' ? text(row.department_id) : row.department_id === null) &&
      (row.kind === 'personal' ? text(row.owner_id) : row.owner_id === null),
  )
  return value as FileSpace
}

/** 校验条目类型、版本及大小；目录和零字节文件分别处理。 */
export function decodeEntry(value: unknown): FileEntry {
  const row = object(value)
  requireValue(
    text(row.id) &&
      text(row.space_id) &&
      nullableId(row.parent_id) &&
      text(row.name) &&
      text(row.created_by),
  )
  requireValue(
    integer(row.version) &&
      (row.kind === 'folder'
        ? row.size_bytes === null
        : row.kind === 'file' && integer(row.size_bytes, 0)),
  )
  requireValue(
    text(row.created_at) &&
      Number.isFinite(Date.parse(row.created_at)) &&
      text(row.updated_at) &&
      Number.isFinite(Date.parse(row.updated_at)),
  )
  return value as FileEntry
}

/** 检查分页外壳，由各业务解码器校验行内容。 */
function page<T>(value: unknown, decode: (row: unknown) => T): FilePage<T> {
  const row = object(value)
  requireValue(Array.isArray(row.items) && (row.next_cursor === null || text(row.next_cursor)))
  return { items: row.items.map(decode), next_cursor: row.next_cursor as string | null }
}

/** 校验根目录到当前目标的路径。 */
function breadcrumbs(value: unknown): Breadcrumb[] {
  requireValue(Array.isArray(value))
  for (const item of value) {
    const row = object(item)
    requireValue(text(row.id) && text(row.name))
  }
  return value as Breadcrumb[]
}

/** 发出单次 JSON 请求，失败不自动重放。 */
async function request(
  path: string,
  signal: AbortSignal,
  method = 'GET',
  body?: object,
): Promise<unknown> {
  return readEnvelope(
    await authenticatedFetch(`/api/files/${path}`, {
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

/** 读取可见空间的一页，不把游标带入其他目录。 */
export async function listSpaces(
  signal: AbortSignal,
  cursor?: string,
): Promise<FilePage<FileSpace>> {
  const query = new URLSearchParams({ limit: '20' })
  if (cursor) query.set('cursor', cursor)
  return page(await request(`spaces?${query}`, signal), decodeSpace)
}

/** 读取目录及其最新空间权限和完整路径。 */
export async function listEntries(
  spaceId: string,
  parentId: string | null,
  signal: AbortSignal,
  cursor?: string,
): Promise<DirectoryPage> {
  const query = new URLSearchParams({ limit: '20' })
  if (parentId) query.set('parent_id', parentId)
  if (cursor) query.set('cursor', cursor)
  const data = await request(`spaces/${encodeURIComponent(spaceId)}/entries?${query}`, signal)
  const row = object(data)
  const space = decodeSpace(row.space)
  requireValue(space.id === spaceId && row.parent_id === parentId)
  const result = page(data, decodeEntry)
  requireValue(
    result.items.every(
      // 防止跨空间或父目录的错误响应污染当前列表。
      (entry) => entry.space_id === spaceId && entry.parent_id === parentId,
    ),
  )
  return { ...result, space, parent_id: parentId, breadcrumbs: breadcrumbs(row.breadcrumbs) }
}

/** 创建目录并取得规范化后的名称。 */
export async function createFolder(
  spaceId: string,
  parentId: string | null,
  name: string,
  signal: AbortSignal,
): Promise<FileEntry> {
  return decodeEntry(
    await request(`spaces/${encodeURIComponent(spaceId)}/folders`, signal, 'POST', {
      name,
      parent_id: parentId,
    }),
  )
}

/** 使用读取时版本重命名，冲突交由表单处理。 */
export async function renameEntry(
  entry: FileEntry,
  name: string,
  signal: AbortSignal,
): Promise<FileEntry> {
  return decodeEntry(
    await request(`entries/${encodeURIComponent(entry.id)}`, signal, 'PATCH', {
      name,
      version: entry.version,
    }),
  )
}

/** 删除冻结版本的条目；删除目录由后端递归处理。 */
export async function deleteEntry(entry: FileEntry, signal: AbortSignal): Promise<void> {
  requireValue(
    (await request(
      `entries/${encodeURIComponent(entry.id)}?version=${entry.version}`,
      signal,
      'DELETE',
    )) === null,
  )
}

/** 上传一个原件；浏览器生成 multipart 边界，绝不手设 Content-Type 或自动重试。 */
export async function uploadFile(
  spaceId: string,
  parentId: string | null,
  file: File,
  signal: AbortSignal,
): Promise<FileEntry> {
  const form = new FormData()
  form.append('file', file)
  const query = parentId ? `?${new URLSearchParams({ parent_id: parentId })}` : ''
  return decodeEntry(
    await readEnvelope(
      await authenticatedFetch(`/api/files/spaces/${encodeURIComponent(spaceId)}/files${query}`, {
        method: 'POST',
        signal,
        body: form,
      }),
    ),
  )
}

/** 下载完整原件，检查传输大小后触发附件保存，并延迟释放对象 URL。 */
export async function downloadFile(entry: FileEntry, signal: AbortSignal): Promise<void> {
  const result = await authenticatedFetch(
    `/api/files/entries/${encodeURIComponent(entry.id)}/download`,
    { signal },
  )
  if (!result.ok) {
    await readEnvelope(result)
    return
  }
  const blob = await result.blob()
  if (signal.aborted) return
  if (blob.size !== entry.size_bytes)
    throw new ApiError('文件传输不完整或文件已变化，请重新查看目录后下载。')
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = entry.name
  document.body.append(anchor)
  anchor.click()
  anchor.remove()
  // 浏览器需要先接管附件；延后回收不会阻止已触发的下载。
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/** 由空间归属映射到共享策略地址，个人策略绝不使用用户 ID。 */
function policyPath(space: FileSpace): string {
  return `upload-limits/${space.kind === 'department' ? `departments/${encodeURIComponent(space.department_id!)}` : space.kind}`
}

/** 读取或更新上传策略，并校验版本与允许大小范围。 */
export async function uploadLimit(
  space: FileSpace,
  signal: AbortSignal,
  input?: { max_file_size_bytes: number; version: number },
): Promise<UploadLimit> {
  const data = await request(policyPath(space), signal, input ? 'PATCH' : 'GET', input)
  const row = object(data)
  requireValue(
    row.scope_type === space.kind &&
      row.department_id === space.department_id &&
      integer(row.max_file_size_bytes, 1, 1099511627776) &&
      integer(row.version),
  )
  requireValue(
    nullableId(row.updated_by) &&
      text(row.updated_at) &&
      Number.isFinite(Date.parse(row.updated_at)),
  )
  return data as UploadLimit
}
