/** 配置状态行为：验证密钥不缓存、默认版本、主动测试和身份/页面取消后迟到响应隔离。 */
import { beforeEach, expect, it, vi } from 'vitest'
import { createTestPinia } from '@tests/support/vitest/mount'
import { authenticate } from '@tests/support/vitest/auth'
import { deferredResponse, response } from '@tests/support/vitest/http'
import { bailianConfigData, modelConfigData } from '@tests/support/data/model-config'
import { useAuthStore } from '@/features/auth/store'
import { updateModelConfigModule, useModelConfigStore } from '../store'

const fetchMock = vi.fn<typeof fetch>()
// 正式状态和 HTTP 解码参与测试，工厂每例隔离，避免共享版本污染。
beforeEach(async () => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  await authenticate(createTestPinia(), fetchMock, true)
})
/** 安装能够读取完整管理快照的契约替身。 */
function management() {
  const data = modelConfigData()
  fetchMock.mockImplementation(async (input) => {
    const url = String(input)
    return response(
      url.endsWith('/catalog/providers')
        ? [data.brand]
        : url.endsWith('/provider-configurations')
          ? [data.provider]
          : url.endsWith('/models')
            ? [data.model]
            : data.selected,
    )
  })
  return data
}

it('加载共享数据，保存供应商省略空密钥，更新默认始终发送原读取版本', async () => {
  const data = management(),
    store = useModelConfigStore()
  await store.load()
  expect(store.ready).toBe(true)
  const pending = deferredResponse()
  fetchMock.mockImplementationOnce(async (_input, init) => {
    expect(JSON.parse(String(init?.body))).not.toHaveProperty('api_key')
    return response({ ...data.provider, version: 2 })
  })
  await store.saveProvider(
    {
      name: '更新',
      provider: 'anthropic',
      api_format: 'messages',
      endpoint_config: { endpoint_id: 'official' },
      api_key: '',
    },
    data.provider,
  )
  expect(JSON.stringify(store.$state)).not.toContain('api_key":"')
  fetchMock.mockReturnValueOnce(pending.promise)
  const loading = store.loadDefault()
  fetchMock.mockResolvedValueOnce(
    response({ ...data.selected, version: 2, model_configuration_id: null, model: null }),
  )
  await store.setDefault(null)
  pending.resolve(response(data.selected))
  await loading
  expect(store.selected?.model).toBeNull()
  expect(store.selected?.version).toBe(2)
})

it('热更新替换滞留的保存动作，保留原状态实例并使用新版 Base URL 响应解码', async () => {
  const data = bailianConfigData(),
    store = useModelConfigStore()
  store.brands = [data.brand]
  store.configurations = [data.provider]
  store.selectedProvider = data.provider.id
  // 模拟接口改版前保留在单例中的旧动作；热更新后必须使用真实新版 HTTP 适配层。
  const staleSave = vi.fn<typeof store.saveProvider>()
  store.saveProvider = staleSave
  const created = { ...data.provider, id: 'new-bailian', name: '新版百炼' }
  fetchMock.mockImplementation(async (input, options) => {
    const url = String(input)
    if (options?.method === 'POST') return response(created)
    if (url.endsWith('/catalog/providers')) return response([data.brand])
    if (url.endsWith('/provider-configurations')) return response([data.provider, created])
    if (url.endsWith('/models')) return response([])
    return response({
      model_configuration_id: null,
      model: null,
      version: 1,
      updated_at: created.updated_at,
    })
  })
  const hot = { data: {}, invalidate: vi.fn<() => void>() }
  updateModelConfigModule({ useModelConfigStore }, hot)
  expect(useModelConfigStore()).toBe(store)
  expect(store.selectedProvider).toBe(data.provider.id)
  expect(store.configurations).toEqual([data.provider])
  await store.saveProvider({
    name: created.name,
    provider: 'bailian',
    api_format: 'chat_completions',
    endpoint_config: created.endpoint_config,
    api_key: 'fake-hmr-key',
  })
  expect(staleSave).not.toHaveBeenCalled()
  expect(hot.invalidate).not.toHaveBeenCalled()
  expect(store.selectedProvider).toBe(created.id)
  expect(store.configurations).toContainEqual(created)
  expect(JSON.stringify(store.$state)).not.toContain('fake-hmr-key')
})

it('停用仅提交目标资源版本与 enabled，重新读取关联可选性', async () => {
  const data = management(),
    store = useModelConfigStore()
  await store.load()
  fetchMock.mockImplementationOnce(async (_url, init) => {
    expect(JSON.parse(String(init?.body))).toEqual({
      version: data.provider.version,
      enabled: false,
    })
    data.provider.enabled = false
    data.provider.version = 2
    data.model.selectable = false
    return response(data.provider)
  })
  await store.setEnabled('provider', data.provider, false)
  expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'PATCH')).toBe(true)
  expect(store.configurations[0]?.enabled).toBe(false)
  expect(store.models[0]?.enabled).toBe(true)
  expect(store.models[0]?.selectable).toBe(false)
  expect(store.selected?.model_configuration_id).toBe(data.model.id)
})

it('热更新取消旧请求，迟到响应不覆盖缓存，新身份监听仍能在退出时清理状态', async () => {
  const data = management(),
    store = useModelConfigStore()
  await store.load()
  const pending = deferredResponse()
  fetchMock.mockReturnValueOnce(pending.promise)
  const reading = store.loadDefault(),
    signal = fetchMock.mock.lastCall?.[1]?.signal
  updateModelConfigModule({ useModelConfigStore }, { data: {}, invalidate: vi.fn<() => void>() })
  expect(signal?.aborted).toBe(true)
  expect(store.defaultLoading).toBe(false)
  expect(store.selected).toEqual(data.selected)
  pending.resolve(response({ ...data.selected, version: 999 }))
  await reading
  expect(store.selected).toEqual(data.selected)
  useAuthStore().logout()
  expect(store.selected).toBeNull()
  expect(store.configurations).toEqual([])
})

it('主动测试不修改默认，离开管理页取消在途测试且不显示取消错误', async () => {
  const data = management(),
    store = useModelConfigStore()
  await store.load()
  fetchMock.mockResolvedValueOnce(
    response({
      latency_ms: 18,
      provider_configuration_version: 1,
      model_version: 1,
      verified: 'streaming_text',
    }),
  )
  await store.test(data.model.id)
  expect(store.tests[data.model.id]?.result?.latency_ms).toBe(18)
  expect(store.selected?.version).toBe(1)
  const pending = deferredResponse()
  fetchMock.mockReturnValueOnce(pending.promise)
  const testing = store.test(data.model.id),
    signal = fetchMock.mock.lastCall?.[1]?.signal
  store.cancelManagement()
  expect(signal?.aborted).toBe(true)
  pending.resolve(response(null, 500, 50000, '失败'))
  await testing
  expect(store.tests[data.model.id]).toBeUndefined()
})

it('退出后迟到的配置读取和失败测试都不能恢复旧账号数据', async () => {
  const data = management(),
    store = useModelConfigStore()
  await store.load()
  const pending = deferredResponse()
  fetchMock.mockReturnValueOnce(pending.promise)
  const testing = store.test(data.model.id)
  useAuthStore().logout()
  pending.resolve(response(null, 200, 20002, '上游鉴权失败'))
  await testing
  expect(store.models).toEqual([])
  expect(store.tests).toEqual({})
  expect(store.selected).toBeNull()
})

// 删除默认方案必须先成功清除默认，不能绕过服务端的默认版本或模型引用限制。
it('删除默认模型先清除默认再删除，保留两次请求各自的版本', async () => {
  const data = management(),
    store = useModelConfigStore()
  await store.load()
  fetchMock.mockResolvedValueOnce(
    response({ ...data.selected, model: null, model_configuration_id: null, version: 2 }),
  )
  fetchMock.mockResolvedValueOnce(response(null))
  await store.remove('model', data.model)
  const writes = fetchMock.mock.calls.filter(
    ([, options]) => options?.method === 'PUT' || options?.method === 'DELETE',
  )
  expect(writes.map(([, options]) => options?.method)).toEqual(['PUT', 'DELETE'])
  expect(JSON.parse(String(writes[0]![1]?.body))).toEqual({
    model_configuration_id: null,
    version: 1,
  })
  expect(String(writes[1]![0])).toContain('version=1')
  expect(store.selected?.model_configuration_id).toBeNull()
  expect(store.models).toEqual([])
})

it('清除默认失败时不删除模型，默认引用和模型配置保持原样', async () => {
  const data = management(),
    store = useModelConfigStore()
  await store.load()
  fetchMock.mockResolvedValueOnce(response(null, 409, 40902, '默认状态已变化'))
  await expect(store.remove('model', data.model)).rejects.toThrow('默认状态已变化')
  expect(fetchMock.mock.calls.some(([, options]) => options?.method === 'DELETE')).toBe(false)
  expect(store.selected?.model_configuration_id).toBe(data.model.id)
  expect(store.models).toHaveLength(1)
})

it('默认清除成功但删除失败时保留模型并明确说明部分成功，不自动回滚默认', async () => {
  const data = management(),
    store = useModelConfigStore()
  await store.load()
  fetchMock.mockResolvedValueOnce(
    response({ ...data.selected, model: null, model_configuration_id: null, version: 2 }),
  )
  fetchMock.mockResolvedValueOnce(response(null, 409, 40902, '模型版本已变化'))
  await expect(store.remove('model', data.model)).rejects.toThrow('全局默认已清除，但模型删除失败')
  expect(store.selected?.model_configuration_id).toBeNull()
  expect(store.models).toHaveLength(1)
})
