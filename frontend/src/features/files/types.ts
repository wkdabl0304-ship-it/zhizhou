/** 资料库公开契约：仅描述服务端可见空间、目录和上传策略，不保存磁盘路径。 */
export type SpaceKind = 'global' | 'department' | 'personal'
export type Capability = 'read' | 'upload' | 'update' | 'delete'

/** 可见空间及当前请求身份能够执行的操作。 */
export interface FileSpace {
  id: string
  kind: SpaceKind
  name: string
  department_id: string | null
  owner_id: string | null
  max_file_size_bytes: number
  capabilities: Capability[]
}

/** 文件与目录共用的可见条目；目录大小为 null，空文件大小为 0。 */
export interface FileEntry {
  id: string
  space_id: string
  parent_id: string | null
  kind: 'file' | 'folder'
  name: string
  size_bytes: number | null
  created_by: string
  version: number
  created_at: string
  updated_at: string
}

/** 按服务端顺序追加的游标分页，游标只用于原查询目标。 */
export interface FilePage<T> {
  items: T[]
  next_cursor: string | null
}

/** 从空间根目录向下排列的目录定位。 */
export interface Breadcrumb {
  id: string
  name: string
}

/** 目录响应同时提供最新权限、上传限制和完整面包屑。 */
export interface DirectoryPage extends FilePage<FileEntry> {
  space: FileSpace
  parent_id: string | null
  breadcrumbs: Breadcrumb[]
}

/** 带乐观并发版本的上传大小策略，个人策略覆盖所有人的个人空间。 */
export interface UploadLimit {
  scope_type: SpaceKind
  department_id: string | null
  max_file_size_bytes: number
  version: number
  updated_by: string | null
  updated_at: string
}

/** 弹窗冻结目标和版本，目录刷新不会把旧草稿提交到另一条目。 */
export type FileAction =
  | { kind: 'create'; space: FileSpace; parentId: string | null }
  | { kind: 'rename' | 'delete'; space: FileSpace; entry: FileEntry }
