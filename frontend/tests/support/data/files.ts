/** 文件测试公开数据：每次创建独立对象，避免用例间共享版本、权限和目录变更。 */
import type { FileEntry, FileSpace, UploadLimit } from '@/features/files/types'

/** 构造本人可维护的个人空间，覆盖只读场景时显式替换 capabilities。 */
export function fileSpace(overrides: Partial<FileSpace> = {}): FileSpace {
  return {
    id: 'space-personal',
    kind: 'personal',
    name: '个人空间',
    department_id: null,
    owner_id: 'user-1',
    max_file_size_bytes: 104857600,
    capabilities: ['read', 'upload', 'update', 'delete'],
    ...overrides,
  }
}

/** 构造真实契约下的文件条目，测试可覆盖目录、版本与父节点。 */
export function fileEntry(overrides: Partial<FileEntry> = {}): FileEntry {
  return {
    id: 'entry-1',
    space_id: 'space-personal',
    parent_id: null,
    kind: 'file',
    name: '山海笔记.txt',
    size_bytes: 6,
    created_by: 'user-1',
    version: 1,
    created_at: '2026-10-29T08:00:00Z',
    updated_at: '2026-10-29T08:00:00Z',
    ...overrides,
  }
}

/** 构造当前空间对应的版本化上传策略。 */
export function filePolicy(space = fileSpace()): UploadLimit {
  return {
    scope_type: space.kind,
    department_id: space.department_id,
    max_file_size_bytes: space.max_file_size_bytes,
    version: 1,
    updated_by: null,
    updated_at: '2026-10-29T08:00:00Z',
  }
}
