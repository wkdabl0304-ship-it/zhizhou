/** 配置表单组件：通过真实表单、模态和目录 HTTP 验证密钥省略、预算校验、冲突草稿和关闭保护。 */
import { beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { defineComponent, h, type Component } from 'vue'
import { TooltipProvider } from 'reka-ui'
import { createTestPinia } from '@tests/support/vitest/mount'
import { authenticate } from '@tests/support/vitest/auth'
import { deferredResponse, response } from '@tests/support/vitest/http'
import { bailianConfigData, modelConfigData } from '@tests/support/data/model-config'
import { useModelConfigStore } from '../store'
import ProviderEditor from '../components/ProviderEditor.vue'
import ModelEditor from '../components/ModelEditor.vue'

const fetchMock = vi.fn<typeof fetch>()
// 每例使用独立真实 Pinia，组件卸载和 Portal 清理由公共 setup 负责。
beforeEach(async () => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  await authenticate(createTestPinia(), fetchMock)
  const store = useModelConfigStore(),
    data = modelConfigData()
  store.brands = [data.brand]
  store.configurations = [data.provider]
  store.models = [data.model]
})

/** 将编辑器置于真实路由中，使未保存离页保护也参与组件生命周期。 */
async function editor(component: Component, props: Record<string, unknown>) {
  const Route = defineComponent({ setup: () => () => h(component, props) })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: Route },
      { path: '/other', component: { template: '<p>另一个页面</p>' } },
    ],
  })
  await router.push('/')
  const Host = defineComponent({
    setup: () => () => h(TooltipProvider, null, { default: () => h(RouterView) }),
  })
  const wrapper = mount(Host, { attachTo: document.body, global: { plugins: [router] } })
  await flushPromises()
  return { wrapper, router }
}
/** 通过 Portal 内的原生输入更新字段，不调用组件私有处理函数。 */
async function fill(name: string, value: string) {
  const input = document.querySelector<HTMLInputElement>(`[name="${name}"]`)!
  input.value = value
  input.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
}
/** 提交当前配置表单并等待异步处理。 */
async function submit() {
  document
    .querySelector('form')!
    .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
  await flushPromises()
}

it('编辑供应商留空密钥不发送密钥，冲突后草稿及旧版本保持不变', async () => {
  const data = modelConfigData()
  // 冲突后自动同步公开快照，但再次提交仍必须使用表单最初读取的版本。
  fetchMock.mockImplementation(async (input, options) => {
    if (options?.method === 'PATCH')
      return response(null, 409, 40902, '模型配置已被修改，请刷新后重试')
    const url = String(input)
    return response(
      url.endsWith('/catalog/providers')
        ? [data.brand]
        : url.endsWith('/provider-configurations')
          ? [{ ...data.provider, name: '远端名称', version: 2 }]
          : url.endsWith('/models')
            ? [data.model]
            : data.selected,
    )
  })
  const { wrapper } = await editor(ProviderEditor, { previous: data.provider })
  expect(document.querySelector<HTMLInputElement>('[name="api_key"]')!.value).toBe('')
  await fill('name', '我的修改')
  await submit()
  expect(document.querySelector('[role="alert"]')!.textContent).toContain('已被修改')
  expect(document.querySelector<HTMLInputElement>('[name="name"]')!.value).toBe('我的修改')
  expect(
    JSON.parse(
      String(fetchMock.mock.calls.find(([, options]) => options?.method === 'PATCH')?.[1]?.body),
    ),
  ).toEqual({
    version: 1,
    name: '我的修改',
    enabled: true,
    api_format: 'messages',
    endpoint_config: { endpoint_id: 'official' },
  })
  await submit()
  expect(
    JSON.parse(
      String(
        fetchMock.mock.calls.filter(([, options]) => options?.method === 'PATCH').at(-1)?.[1]?.body,
      ),
    ).version,
  ).toBe(1)
  wrapper.unmount()
})

it('百炼编辑显示完整地址，粘贴后保存规范 URL 且留空密钥保持省略', async () => {
  const { provider, brand } = bailianConfigData(),
    store = useModelConfigStore()
  store.brands = [brand]
  store.configurations = [provider]
  store.models = []
  const address = 'https://ws-next.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1'
  // 保存后重新读取管理快照，按 HTTP 职责返回更新后的公开资源。
  fetchMock.mockImplementation(async (url, options) => {
    if (options?.method === 'PATCH')
      return response({ ...provider, version: 2, endpoint_config: { base_url: address } })
    if (String(url).endsWith('/catalog/providers')) return response([brand])
    if (String(url).endsWith('/provider-configurations'))
      return response([{ ...provider, version: 2, endpoint_config: { base_url: address } }])
    if (String(url).endsWith('/models')) return response([])
    return response({
      model_configuration_id: null,
      model: null,
      version: 1,
      updated_at: provider.updated_at,
    })
  })
  const { wrapper } = await editor(ProviderEditor, { previous: provider })
  expect(document.querySelector<HTMLInputElement>('[name="base_url"]')!.value).toBe(
    provider.endpoint_config.base_url,
  )
  expect(document.querySelector('[name="endpoint"]')).toBeNull()
  expect(document.querySelector('[name="workspace"]')).toBeNull()
  await fill('base_url', `  ${address}/  `)
  await submit()
  const write = fetchMock.mock.calls.find(([, options]) => options?.method === 'PATCH')!
  expect(JSON.parse(String(write[1]?.body))).toEqual({
    version: 1,
    name: provider.name,
    enabled: true,
    api_format: 'chat_completions',
    endpoint_config: { base_url: address },
  })
  expect(store.configurations[0]?.endpoint_config).toEqual({ base_url: address })
  wrapper.unmount()
})

it('新建百炼提示粘贴地址，切换品牌会清除其他供应商的地址', async () => {
  const { brand } = bailianConfigData(),
    store = useModelConfigStore()
  store.brands = [brand, modelConfigData().brand]
  const { wrapper } = await editor(ProviderEditor, {})
  expect(document.querySelector<HTMLInputElement>('[name="base_url"]')!.value).toBe('')
  await fill('name', '粘贴地址')
  await fill('api_key', 'fake-key')
  await submit()
  expect(document.querySelector('[role="alert"]')!.textContent).toContain('OpenAI 兼容地址')
  expect(fetchMock).not.toHaveBeenCalled()
  await fill('base_url', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
  const select = document.querySelector<HTMLSelectElement>('[name="provider"]')!
  select.value = 'anthropic'
  select.dispatchEvent(new Event('change', { bubbles: true }))
  await flushPromises()
  expect(document.querySelector('[name="base_url"]')).toBeNull()
  select.value = 'bailian'
  select.dispatchEvent(new Event('change', { bubbles: true }))
  await flushPromises()
  expect(document.querySelector<HTMLInputElement>('[name="base_url"]')!.value).toBe('')
  wrapper.unmount()
})

it('目录默认预算超过输出时阻止写入，修改后只发送选中推理分支', async () => {
  const data = modelConfigData()
  fetchMock.mockResolvedValueOnce(response([data.catalog]))
  const { wrapper } = await editor(ModelEditor, { provider: data.provider })
  await fill('name', '新方案')
  await fill('max_output_tokens', '4096')
  await submit()
  expect(document.querySelector('[role="alert"]')!.textContent).toContain('必须小于')
  expect(fetchMock).toHaveBeenCalledTimes(1)
  await fill('max_output_tokens', '8192')
  fetchMock.mockResolvedValueOnce(
    response({ ...data.model, name: '新方案', max_output_tokens: 8192 }),
  )
  await submit()
  expect(JSON.parse(String(fetchMock.mock.lastCall?.[1]?.body)).reasoning).toEqual({
    mode: 'default',
  })
  expect(useModelConfigStore().models[0]?.name).toBe('新方案')
  wrapper.unmount()
})

it('未保存的表单离页先确认，继续编辑保留内容，放弃后才允许导航', async () => {
  const { wrapper, router } = await editor(ProviderEditor, {})
  await fill('name', '未保存')
  const navigating = router.push('/other')
  await flushPromises()
  expect(document.body.textContent).toContain('放弃未保存的更改？')
  const keep = [...document.querySelectorAll('button')].find(
    (button) => button.textContent === '继续编辑',
  )!
  keep.click()
  await navigating
  await flushPromises()
  expect(router.currentRoute.value.path).toBe('/')
  expect(document.querySelector<HTMLInputElement>('[name="name"]')!.value).toBe('未保存')
  const next = router.push('/other')
  await flushPromises()
  const discard = [...document.querySelectorAll('button')].find(
    (button) => button.textContent === '放弃更改',
  )!
  discard.click()
  await next
  await flushPromises()
  expect(router.currentRoute.value.path).toBe('/other')
  wrapper.unmount()
})

it('失效目录方案显示明确占位，选用可用模型后可修复原方案', async () => {
  const data = modelConfigData()
  fetchMock.mockResolvedValueOnce(response([data.catalog]))
  const { wrapper } = await editor(ModelEditor, {
    provider: data.provider,
    previous: { ...data.model, catalog_model_id: 'retired:model', catalog: null, available: false },
  })
  const selector = document.querySelector<HTMLSelectElement>('[name="catalog_model_id"]')!
  expect(selector.value).toBe('')
  await submit()
  expect(document.querySelector('[role="alert"]')!.textContent).toContain('可用的目录模型')
  selector.value = data.catalog.catalog_model_id
  selector.dispatchEvent(new Event('change', { bubbles: true }))
  await flushPromises()
  fetchMock.mockResolvedValueOnce(response({ ...data.model, version: 2 }))
  await submit()
  expect(JSON.parse(String(fetchMock.mock.lastCall?.[1]?.body))).toMatchObject({
    version: 1,
    catalog_model_id: data.catalog.catalog_model_id,
  })
  wrapper.unmount()
})

it('目录读取未完成仍允许关闭，卸载后取消请求并忽略迟到结果', async () => {
  const data = modelConfigData(),
    pending = deferredResponse(),
    onClose = vi.fn<() => void>()
  fetchMock.mockReturnValueOnce(pending.promise)
  const { wrapper } = await editor(ModelEditor, { provider: data.provider, onClose })
  const signal = fetchMock.mock.lastCall?.[1]?.signal
  const close = document.querySelector<HTMLButtonElement>('[aria-label="关闭"]')!
  close.click()
  await flushPromises()
  expect(onClose).toHaveBeenCalledTimes(1)
  wrapper.unmount()
  expect(signal?.aborted).toBe(true)
  pending.resolve(response([data.catalog]))
  await flushPromises()
  expect(useModelConfigStore().models).toHaveLength(1)
})
