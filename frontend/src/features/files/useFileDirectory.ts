/** 文件目录生命周期：隔离空间分页与目录分页，取消切换请求并阻止迟到结果覆盖。 */
import { onScopeDispose, ref, watch } from 'vue'
import { useAuthStore } from '@/features/auth/store'
import { ApiError } from '@/features/auth/authenticated'
import * as api from './api'
import { fileError } from './format'
import type { Breadcrumb, FileEntry, FileSpace } from './types'

/** 编排当前页面的数据读取；目录定位由路由提供，写入操作完成后调用 reload。 */
export function useFileDirectory(target: () => { spaceId: string; parentId: string | null }) {
  const auth = useAuthStore()
  const spaces = ref<FileSpace[]>([]),
    spaceCursor = ref<string | null>(null)
  const spacesLoading = ref(false),
    spacesError = ref('')
  const space = ref<FileSpace | null>(null),
    entries = ref<FileEntry[]>([])
  const breadcrumbs = ref<Breadcrumb[]>([]),
    cursor = ref<string | null>(null)
  const loading = ref(false),
    error = ref('')
  let directoryRequest: AbortController | undefined, spaceRequest: AbortController | undefined
  let previousTarget = ''

  /** 读取空间分页，失败保留已有空间；失效游标只重新读取首页。 */
  async function loadSpaces(more = false): Promise<void> {
    if (more && (spacesLoading.value || !spaceCursor.value)) return
    spaceRequest?.abort()
    const controller = (spaceRequest = new AbortController())
    spacesLoading.value = true
    spacesError.value = ''
    try {
      const page = await api.listSpaces(controller.signal, more ? spaceCursor.value! : undefined)
      if (controller.signal.aborted) return
      const merged = new Map(
        (more ? spaces.value : []).map(
          // 同一实时分页可能重复，按公开 ID 去重并保留服务端次序。
          (item) => [item.id, item],
        ),
      )
      for (const item of page.items) merged.set(item.id, item)
      spaces.value = [...merged.values()]
      spaceCursor.value = page.next_cursor
    } catch (failure) {
      if (controller.signal.aborted) return
      if (more && failure instanceof ApiError && failure.status === 422) {
        await loadSpaces()
        return
      }
      spacesError.value = fileError(failure)
    } finally {
      if (spaceRequest === controller) spacesLoading.value = false
    }
  }

  /** 读取当前目录；定位改变立即清空旧内容，分页失败则保留已读条目。 */
  async function reload(more = false): Promise<void> {
    if (more && (loading.value || !cursor.value)) return
    directoryRequest?.abort()
    const controller = (directoryRequest = new AbortController())
    const { spaceId, parentId } = target()
    const key = JSON.stringify([spaceId, parentId])
    error.value = ''
    if (!more) {
      cursor.value = null
      if (key !== previousTarget) {
        entries.value = []
        breadcrumbs.value = []
        space.value = null
      }
    }
    previousTarget = key
    if (!spaceId) {
      loading.value = false
      return
    }
    loading.value = true
    try {
      const result = await api.listEntries(
        spaceId,
        parentId,
        controller.signal,
        more ? cursor.value! : undefined,
      )
      if (controller.signal.aborted) return
      space.value = result.space
      const index = spaces.value.findIndex(
        // 目录响应的能力与限制比空间缓存更新，及时替换对应摘要。
        (item) => item.id === result.space.id,
      )
      if (index >= 0) spaces.value[index] = result.space
      const merged = new Map((more ? entries.value : []).map((item) => [item.id, item]))
      for (const item of result.items) merged.set(item.id, item)
      entries.value = [...merged.values()]
      breadcrumbs.value = result.breadcrumbs
      cursor.value = result.next_cursor
    } catch (failure) {
      if (controller.signal.aborted) return
      if (more && failure instanceof ApiError && failure.status === 422) {
        await reload()
        return
      }
      error.value = fileError(failure)
      if (failure instanceof ApiError && [403, 404].includes(failure.status)) {
        space.value = null
        entries.value = []
        breadcrumbs.value = []
        cursor.value = null
      }
    } finally {
      if (directoryRequest === controller) loading.value = false
    }
  }

  // URL 是目录定位的唯一来源，刷新、前进后退与复制链接使用同一读取路径。
  watch(
    () => JSON.stringify(target()),
    () => {
      void reload()
    },
    { immediate: true },
  )
  // 身份和部门变化使所有游标失效，清除旧数据后重新查询服务端可见范围。
  watch(
    () => JSON.stringify([auth.accessToken, auth.user?.department, auth.user?.grants]),
    () => {
      spaces.value = []
      spaceCursor.value = null
      space.value = null
      entries.value = []
      breadcrumbs.value = []
      cursor.value = null
      spaceRequest?.abort()
      directoryRequest?.abort()
      if (!auth.isAuthenticated) return
      void loadSpaces()
      void reload()
    },
  )
  onScopeDispose(() => {
    directoryRequest?.abort()
    spaceRequest?.abort()
  })
  return {
    spaces,
    spaceCursor,
    spacesLoading,
    spacesError,
    space,
    entries,
    breadcrumbs,
    cursor,
    loading,
    error,
    loadSpaces,
    reload,
  }
}
