/** 聊天允许范围状态：独立于管理目录，按账号及读取序号隔离响应，接口结果不被表单修改。 */
import { computed, onScopeDispose, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { ApiError, authenticatedFetch, readEnvelope } from '@/features/auth/authenticated'
import { useAuthStore } from '@/features/auth/store'
import { decodeOptions } from './contract'
import type { ModelOptions } from './types'
export const useModelSelectionStore = defineStore('model-selection', () => {
  const auth = useAuthStore(),
    options = ref<ModelOptions | null>(null),
    loading = ref(false),
    error = ref('')
  const models = computed(() => options.value?.providers.flatMap((item) => item.models) ?? [])
  let revision = 0,
    controller: AbortController | undefined
  /** 读取当前账号允许范围，旧请求取消或迟到时不得覆盖最新快照。 */
  async function load(): Promise<void> {
    if (!auth.isAuthenticated) return
    const stamp = ++revision
    controller?.abort()
    const request = (controller = new AbortController())
    loading.value = true
    try {
      const result = decodeOptions(
        await readEnvelope(
          await authenticatedFetch('/api/model-config/options', { signal: request.signal }),
        ),
      )
      if (stamp === revision && !request.signal.aborted) {
        options.value = result
        error.value = ''
      }
    } catch (failure) {
      if (stamp === revision && !request.signal.aborted)
        error.value = failure instanceof ApiError ? failure.message : '模型选项读取失败，请重试'
    } finally {
      if (stamp === revision) loading.value = false
    }
  }
  /** 退出或销毁时取消读取并清理账号缓存，不保留上一身份的模型范围。 */
  function clear(): void {
    revision++
    controller?.abort()
    options.value = null
    error.value = ''
    loading.value = false
  }
  watch(
    () => auth.accessToken,
    (token, previous) => {
      if (previous && token !== previous) clear()
    },
    { flush: 'sync' },
  )
  onScopeDispose(clear)
  return { options, models, loading, error, load }
})
