/** 模型配置状态：隔离账号与迟到请求，协调管理页、默认展示及仅在内存中的测试记录。 */
import { computed, onScopeDispose, ref, watch } from 'vue'
import { acceptHMRUpdate, defineStore, getActivePinia } from 'pinia'
import { useAuthStore } from '@/features/auth/store'
import { ApiError } from '@/features/auth/authenticated'
import * as api from './api'
import type {
  DefaultModel,
  ModelConfiguration,
  ModelInput,
  ProviderConfiguration,
  ProviderInfo,
  ProviderInput,
  ProviderPatch,
  TestResult,
} from './types'

/** 将服务端固定文案用于界面；未知错误不展示堆栈和请求内容。 */
export function explainConfigError(error: unknown): string {
  return error instanceof ApiError ? error.message : '请求未完成，请稍后重试'
}
export const useModelConfigStore = defineStore('model-config', () => {
  const auth = useAuthStore()
  const brands = ref<ProviderInfo[]>([]),
    configurations = ref<ProviderConfiguration[]>([]),
    models = ref<ModelConfiguration[]>([])
  const selected = ref<DefaultModel | null>(null),
    selectedProvider = ref('')
  const loading = ref(false),
    loadError = ref(''),
    defaultLoading = ref(false),
    defaultError = ref('')
  const ready = computed(() => !!selected.value?.model?.available && !defaultError.value)
  const tests = ref<Record<string, { running: boolean; result?: TestResult; error?: string }>>({})
  const controllers = new Set<AbortController>(),
    managementControllers = new Set<AbortController>()
  let epoch = 0,
    managementRevision = 0,
    defaultRevision = 0

  /** 执行一次受账号与生命周期保护的请求，取消后即使替身仍返回也拒绝提交结果。 */
  async function run<T>(work: (signal: AbortSignal) => Promise<T>, management = true): Promise<T> {
    const controller = new AbortController(),
      version = epoch
    controllers.add(controller)
    if (management) managementControllers.add(controller)
    try {
      const result = await work(controller.signal)
      if (controller.signal.aborted || version !== epoch)
        throw new DOMException('请求已取消', 'AbortError')
      return result
    } catch (error) {
      if (controller.signal.aborted || version !== epoch)
        throw new DOMException('请求已取消', 'AbortError')
      throw error
    } finally {
      controllers.delete(controller)
      managementControllers.delete(controller)
    }
  }
  /** 读取全局默认，最新请求优先；保留明确错误供聊天页重试。 */
  async function loadDefault(): Promise<void> {
    if (!auth.isAuthenticated) return
    const revision = ++defaultRevision
    defaultLoading.value = true
    try {
      const data = await run(api.getDefault, false)
      if (revision === defaultRevision) {
        selected.value = data
        defaultError.value = ''
      }
    } catch (error) {
      if (
        revision === defaultRevision &&
        !(error instanceof DOMException && error.name === 'AbortError')
      )
        defaultError.value = explainConfigError(error)
    } finally {
      if (revision === defaultRevision) defaultLoading.value = false
    }
  }
  /** 原子更新管理快照，不让部分失败的列表与旧默认混合。 */
  async function load(): Promise<void> {
    if (!auth.isAuthenticated) return
    const revision = ++managementRevision
    loading.value = true
    loadError.value = ''
    try {
      const data = await run(api.loadManagement)
      if (revision !== managementRevision) return
      brands.value = data.brands
      configurations.value = data.configurations
      models.value = data.models
      defaultRevision++
      selected.value = data.selected
      defaultLoading.value = false
      defaultError.value = ''
      if (!configurations.value.some((item) => item.id === selectedProvider.value))
        selectedProvider.value = configurations.value[0]?.id ?? ''
    } catch (error) {
      if (
        revision === managementRevision &&
        !(error instanceof DOMException && error.name === 'AbortError')
      )
        loadError.value = explainConfigError(error)
    } finally {
      if (revision === managementRevision) loading.value = false
    }
  }
  /** 保存供应商公开响应，密钥不进入 store；旧测试自动因版本变化而失效。 */
  async function saveProvider(
    body: ProviderInput,
    previous?: ProviderConfiguration,
  ): Promise<void> {
    const result = await run((signal) => {
      if (!previous) return api.createProvider(body, signal)
      const patch: ProviderPatch = {
        version: previous.version,
        name: body.name,
        api_format: body.api_format,
        endpoint_config: body.endpoint_config,
        ...(body.enabled === undefined ? {} : { enabled: body.enabled }),
      }
      if (body.api_key.trim()) patch.api_key = body.api_key
      return api.patchProvider(previous.id, patch, signal)
    })
    configurations.value = [...configurations.value.filter((item) => item.id !== result.id), result]
    selectedProvider.value = result.id
    // 名称、格式或凭据更新可能影响目录能力与默认概要，重新读取服务端的最终状态。
    await load()
  }
  /** 保存模型方案，更新当前默认概要时沿用同一份服务端结果。 */
  async function saveModel(body: ModelInput, previous?: ModelConfiguration): Promise<void> {
    const result = await run((signal) =>
      previous
        ? api.patchModel(
            previous.id,
            {
              version: previous.version,
              name: body.name,
              catalog_model_id: body.catalog_model_id,
              reasoning: body.reasoning,
              max_output_tokens: body.max_output_tokens,
              ...(body.enabled === undefined ? {} : { enabled: body.enabled }),
              ...(body.reasoning_policy === undefined
                ? {}
                : { reasoning_policy: body.reasoning_policy }),
            },
            signal,
          )
        : api.createModel(body, signal),
    )
    models.value = [...models.value.filter((item) => item.id !== result.id), result]
    if (selected.value?.model_configuration_id === result.id)
      selected.value = { ...selected.value, model: result }
  }
  /** 按资源版本启停并重读关联可选性，不改写子方案状态或默认引用。 */
  async function setEnabled(
    kind: 'provider' | 'model',
    item: ProviderConfiguration | ModelConfiguration,
    enabled: boolean,
  ): Promise<void> {
    await run<ProviderConfiguration | ModelConfiguration>((signal) =>
      kind === 'provider'
        ? api.patchProvider(item.id, { version: item.version, enabled }, signal)
        : api.patchModel(item.id, { version: item.version, enabled }, signal),
    )
    await load()
    if (loadError.value) throw new ApiError(`启停已保存，${loadError.value}，请刷新确认`)
  }
  /** 切换或清除默认，写成功后取消旧默认读取结果对本地状态的覆盖。 */
  async function setDefault(id: string | null): Promise<void> {
    if (!selected.value) throw new ApiError('请先刷新默认模型状态')
    const version = selected.value.version
    const result = await run((signal) => api.putDefault(id, version, signal))
    defaultRevision++
    defaultLoading.value = false
    selected.value = result
    defaultError.value = ''
  }
  /** 删除资源；默认模型先清除默认，任一步失败都停止后续写入并保留实际已完成状态。 */
  async function remove(
    kind: 'provider' | 'model',
    item: ProviderConfiguration | ModelConfiguration,
  ): Promise<void> {
    let cleared = false
    if (kind === 'model' && selected.value?.model_configuration_id === item.id) {
      await setDefault(null)
      cleared = true
    }
    try {
      await run((signal) =>
        kind === 'provider'
          ? api.deleteProvider(item.id, item.version, signal)
          : api.deleteModel(item.id, item.version, signal),
      )
    } catch (failure) {
      if (cleared)
        throw new ApiError('全局默认已清除，但模型删除失败：' + explainConfigError(failure))
      throw failure
    }
    if (kind === 'provider') {
      configurations.value = configurations.value.filter((row) => row.id !== item.id)
      if (selectedProvider.value === item.id)
        selectedProvider.value = configurations.value[0]?.id ?? ''
    } else {
      models.value = models.value.filter((row) => row.id !== item.id)
      delete tests.value[item.id]
    }
  }
  /** 主动验证文本流，重复点击合并；过期结果保留版本供 UI 标记，不自动设置默认。 */
  async function test(id: string): Promise<void> {
    if (tests.value[id]?.running) return
    const state = { running: true } as { running: boolean; result?: TestResult; error?: string }
    tests.value[id] = state
    try {
      const result = await run((signal) => api.testModel(id, signal))
      if (models.value.some((item) => item.id === id)) tests.value[id] = { running: false, result }
    } catch (error) {
      if (!(error instanceof DOMException && error.name === 'AbortError'))
        tests.value[id] = { running: false, error: explainConfigError(error) }
    } finally {
      if (tests.value[id] === state || tests.value[id]?.running) delete tests.value[id]
    }
  }
  /** 离开管理页时取消其请求，保留默认摘要与已完成的非秘密缓存。 */
  function cancelManagement(): void {
    managementRevision++
    loading.value = false
    for (const controller of managementControllers) controller.abort()
    managementControllers.clear()
  }
  /** 退出、切换账号或销毁状态容器时清理缓存与全部在途请求。 */
  function clear(): void {
    epoch++
    defaultRevision++
    cancelManagement()
    for (const controller of controllers) controller.abort()
    controllers.clear()
    brands.value = []
    configurations.value = []
    models.value = []
    selected.value = null
    selectedProvider.value = ''
    tests.value = {}
    defaultLoading.value = false
    defaultError.value = ''
    loadError.value = ''
  }
  // 即使管理页已卸载，旧身份也不能继续写入配置缓存。
  const stopAuthWatch = watch(
    () => auth.accessToken,
    (token, previous) => {
      if (previous && token !== previous) clear()
    },
    { flush: 'sync' },
  )
  /** 热更新前释放旧请求和身份监听，保留公开缓存供 Pinia 交给新版动作与 getter。 */
  function prepareHotUpdate(): void {
    stopAuthWatch()
    epoch++
    defaultRevision++
    cancelManagement()
    for (const controller of controllers) controller.abort()
    controllers.clear()
    defaultLoading.value = false
    for (const [id, state] of Object.entries(tests.value)) if (state.running) delete tests.value[id]
  }
  onScopeDispose(clear)
  return {
    brands,
    configurations,
    models,
    selected,
    selectedProvider,
    loading,
    loadError,
    defaultLoading,
    defaultError,
    ready,
    tests,
    loadDefault,
    load,
    saveProvider,
    saveModel,
    setEnabled,
    setDefault,
    remove,
    test,
    cancelManagement,
    prepareHotUpdate,
  }
})

/** 更新开发页面正在使用的配置动作，避免旧闭包继续按历史接口格式解码保存响应。 */
export function updateModelConfigModule(
  module: Record<string, unknown> | undefined,
  hot: Pick<NonNullable<ImportMeta['hot']>, 'data' | 'invalidate'>,
): void {
  const pinia = getActivePinia()
  if (!pinia || !module) return
  useModelConfigStore(pinia).prepareHotUpdate()
  acceptHMRUpdate(useModelConfigStore, hot)(module)
}

if (import.meta.hot) {
  const hot = import.meta.hot
  // API 边界变化会传播到此模块；只替换 store 动作，保留侧栏和编辑器的组件实例。
  hot.accept((module) => updateModelConfigModule(module, hot))
}
