/** 组织目录生命周期：筛选与授权变化重置游标，取消请求并隔离迟到响应。 */
import { computed, onScopeDispose, ref, shallowRef, watch, type Ref } from 'vue'
import { ApiError } from '@/features/auth/authenticated'
import { useAuthStore } from '@/features/auth/store'
import { list } from './api'
import type { Query } from './types'

/** 为一个已授权目录提供分页和重试，依赖变化后不混合不同范围的记录。 */
export function useDirectory<T extends { id: string }>(
  path: Ref<string>,
  query: Ref<Query>,
  decode: (value: unknown) => T,
) {
  const auth = useAuthStore()
  const items = shallowRef<T[]>([]),
    cursor = ref<string | null>(null),
    loading = ref(false),
    error = ref('')
  let controller: AbortController | undefined,
    revision = 0
  const identity = computed(() => JSON.stringify([auth.accessToken, auth.user?.grants]))

  /** 载入第一页或下一页；筛选与授权无效的游标自动回到第一页，写操作不会自动重放。 */
  async function load(more = false): Promise<void> {
    if (!path.value || !auth.isAuthenticated || (more && (!cursor.value || loading.value))) return
    controller?.abort()
    const active = (controller = new AbortController()),
      version = ++revision
    loading.value = true
    error.value = ''
    if (!more) {
      items.value = []
      cursor.value = null
    }
    try {
      const result = await list(
        path.value,
        { ...query.value, ...(more ? { cursor: cursor.value! } : {}) },
        decode,
        active.signal,
      )
      if (version !== revision || active.signal.aborted) return
      // 游标翻页时去重，避免目录更新导致同一账号出现两个操作入口。
      items.value = [
        ...new Map([...items.value, ...result.items].map((row) => [row.id, row])).values(),
      ]
      cursor.value = result.next_cursor
    } catch (failure) {
      if (version !== revision || active.signal.aborted) return
      if (more && failure instanceof ApiError && failure.code === 42200) {
        await load()
        return
      }
      error.value = failure instanceof ApiError ? failure.message : '目录暂时无法加载，请稍后重试'
    } finally {
      if (version === revision) loading.value = false
    }
  }

  /** 释放前一次范围的数据与请求，禁止退出账号后的响应重新填入目录。 */
  function clear(): void {
    revision++
    controller?.abort()
    items.value = []
    cursor.value = null
    loading.value = false
    error.value = ''
  }

  // 路径、筛选或授权的任一变化都使既有游标失效。
  watch(
    [path, query, identity],
    () => {
      clear()
      void load()
    },
    { immediate: true },
  )
  onScopeDispose(clear)
  return { items, cursor, loading, error, load }
}
