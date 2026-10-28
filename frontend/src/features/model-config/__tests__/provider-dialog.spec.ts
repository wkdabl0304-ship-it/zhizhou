/** 供应商弹窗回归：通过可见控件验证自动配置、失败恢复、旧引用及草稿生命周期。 */
import { beforeEach, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { TooltipProvider } from 'reka-ui'
import { createTestPinia } from '@tests/support/vitest/mount'
import { authenticate } from '@tests/support/vitest/auth'
import { useAuthStore } from '@/features/auth/store'
import { deferredResponse, response } from '@tests/support/vitest/http'
import { modelConfigData } from '@tests/support/data/model-config'
import { useModelConfigStore } from '../store'
import ProviderDialog from '../components/ProviderDialog.vue'
import ModelManagementView from '@/views/ModelManagementView.vue'
import type { ModelConfiguration, ProviderConfiguration, ProviderInfo } from '../types'

const fetchMock = vi.fn<typeof fetch>()
let data: ReturnType<typeof modelConfigData>
let connections: ProviderConfiguration[], models: ModelConfiguration[]
let brands: ProviderInfo[]
/** 每例重建公开服务快照；请求替身只模拟正式接口响应，不绕过界面处理。 */
beforeEach(async () => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  await authenticate(createTestPinia(), fetchMock, true)
  data = modelConfigData()
  connections = [data.provider]
  models = []
  brands = [data.brand]
  fetchMock.mockImplementation(async (input, init) => {
    const url = String(input)
    if (url.includes('/catalog/models?')) return response([data.catalog])
    if (url.endsWith('/catalog/providers')) return response(brands)
    if (url.endsWith('/provider-configurations')) return response(connections)
    if (url.endsWith('/default')) return response(data.selected)
    if (init?.method === 'POST' && url.endsWith('/models')) {
      models = [{ ...data.model, ...JSON.parse(String(init.body)) }]
      return response(models[0])
    }
    if (init?.method === 'PATCH') {
      const patch = JSON.parse(String(init.body))
      const id = url.split('/').at(-1)
      if (url.includes('/provider-configurations/')) {
        // 多连接场景只更新目标连接，模型可选性按各自归属重新计算。
        connections = connections.map((item) =>
          item.id === id ? { ...item, ...patch, version: item.version + 1 } : item,
        )
        models = models.map((item) => ({
          ...item,
          selectable:
            item.enabled &&
            !!connections.find((connection) => connection.id === item.provider_configuration_id)
              ?.enabled,
        }))
        return response(connections.find((item) => item.id === id))
      }
      models = models.map((item) =>
        item.id === id
          ? {
              ...item,
              ...patch,
              version: item.version + 1,
              selectable:
                (patch.enabled ?? item.enabled) &&
                !!connections.find((connection) => connection.id === item.provider_configuration_id)
                  ?.enabled,
            }
          : item,
      )
      return response(models.find((item) => item.id === id))
    }
    if (url.endsWith('/models')) return response(models)
    throw new Error(`未声明的测试请求：${url}`)
  })
  const store = useModelConfigStore()
  store.brands = brands
  store.configurations = connections
  store.models = models
  store.selected = data.selected
})

/** 将弹窗放入真实路由与 Tooltip 环境，验证 Portal 和离页保护。 */
async function page(view = false, onClose = vi.fn<() => void>()) {
  const Route = defineComponent({
    setup: () => () =>
      view ? h(ModelManagementView) : h(ProviderDialog, { brand: data.brand, onClose }),
  })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: Route },
      { path: '/other', component: { template: '<p>其他页面</p>' } },
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

/** 点击最上层弹窗中明确命名的按钮，避免操作已被遮罩隔离的底层面板。 */
async function click(label: string) {
  const dialogs = document.querySelectorAll('[role="dialog"]')
  const root = dialogs[dialogs.length - 1] ?? document
  const target = [...root.querySelectorAll<HTMLButtonElement>('button')].find(
    (button) => button.textContent?.trim() === label || button.getAttribute('aria-label') === label,
  )
  expect(target).toBeTruthy()
  target!.focus()
  target!.click()
  await flushPromises()
}

it('首页四个品牌均展示，未配置供应商也能打开弹窗查看目录', async () => {
  const names = {
    openai: 'OpenAI',
    anthropic: 'Anthropic',
    deepseek: 'DeepSeek',
    bailian: '阿里云百炼',
  }
  brands = Object.entries(names).map(([provider, display_name]) => ({
    ...data.brand,
    provider: provider as ProviderInfo['provider'],
    display_name,
  }))
  connections = []
  await page(true)
  expect(document.querySelectorAll('.provider-brand-card')).toHaveLength(4)
  expect(document.querySelector('[aria-label="全局默认模型"]')).toBeNull()
  expect(document.querySelector('h1')?.textContent).toBe('模型管理')
  expect(document.querySelector('h2')?.textContent).toContain('模型供应商')
  expect(document.querySelector('.model-management-title-row')?.textContent).toContain(
    'MODEL PROVIDERS',
  )
  expect(document.body.textContent).not.toContain('连接你的供应商，开启适合自己的模型。')
  expect(document.body.textContent).not.toContain('返回聊天')
  expect(document.body.textContent).not.toContain('刷新配置')
  const logos = [...document.querySelectorAll<HTMLImageElement>('.provider-brand-card img')].map(
    (image) => decodeURIComponent(image.getAttribute('src') ?? ''),
  )
  expect(logos).toEqual(
    ['OpenAI', 'Anthropic', 'DeepSeek', 'BaiLian'].map((name) =>
      expect.stringContaining('<title>' + name + '</title>'),
    ),
  )
  expect(document.body.textContent).not.toContain('添加模型方案')
  await click('配置 Anthropic')
  expect(document.querySelector('[role="dialog"]')?.textContent).toContain(
    data.catalog.display_name,
  )
  const toggle = document.querySelector<HTMLButtonElement>(
    `[role="switch"][aria-label="启用模型 ${data.catalog.display_name}"]`,
  )!
  expect(toggle.disabled).toBe(true)
  expect(document.body.textContent).toContain('还没有连接')
  expect(document.querySelector('[name="name"]')).toBeNull()
  await click('添加连接')
  expect(document.querySelectorAll('[role="dialog"]')).toHaveLength(2)
  expect(document.querySelector('[name="provider"]')).toBeNull()
  expect(document.querySelector<HTMLInputElement>('[name="name"]')?.value).toBe('Anthropic')
})

it('首次开关只创建一次配置且不设默认，等待保存时保留关闭状态并禁止重复点击', async () => {
  await page()
  const pending = deferredResponse()
  fetchMock.mockReturnValueOnce(pending.promise)
  const toggle = document.querySelector<HTMLButtonElement>(
    '[role="switch"][aria-label^="启用模型"]',
  )!
  toggle.click()
  await flushPromises()
  toggle.click()
  expect(toggle.disabled).toBe(true)
  expect(toggle.getAttribute('aria-checked')).toBe('false')
  expect(document.querySelector<HTMLButtonElement>('[aria-label="关闭"]')!.disabled).toBe(true)
  const writes = fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')
  expect(writes).toHaveLength(1)
  expect(JSON.parse(String(writes[0]![1]?.body))).toMatchObject({
    name: data.catalog.display_name,
    catalog_model_id: data.catalog.catalog_model_id,
    reasoning: data.catalog.reasoning.default,
    enabled: true,
  })
  pending.resolve(response({ ...data.model, name: data.catalog.display_name }))
  await flushPromises()
  expect(document.querySelector('[aria-label^="启用模型"]')?.getAttribute('aria-checked')).toBe(
    'true',
  )
  expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'PUT')).toBe(false)
  expect(document.querySelector('.catalog-model-list')?.nextElementSibling).toBeNull()
  expect(document.body.textContent).not.toContain('模型已启用，可手动设为默认。')
})

it('启停失败保留原状态，版本冲突显示服务端错误，可读取最新配置后重试', async () => {
  models = [data.model]
  useModelConfigStore().models = models
  await page()
  fetchMock.mockResolvedValueOnce(response(null, 409, 40902, '模型配置已被修改，请刷新后重试'))
  await click(`启用模型 ${data.model.name}`)
  expect(document.querySelector('[aria-label^="启用模型"]')?.getAttribute('aria-checked')).toBe(
    'true',
  )
  expect(document.querySelector('[role="alert"]')?.textContent).toContain('已被修改')
  expect(document.querySelector('.catalog-model-list')?.nextElementSibling).toBeNull()
  await click(`启用模型 ${data.model.name}`)
  expect(document.querySelector('[aria-label^="启用模型"]')?.getAttribute('aria-checked')).toBe(
    'false',
  )
  expect(document.querySelectorAll('[role="dialog"]')).toHaveLength(1)
  expect(document.body.textContent).not.toContain('配置已更新')
})

it('停用连接不改模型启用标记，旧方案和默认 ID 保持不变', async () => {
  models = [data.model, { ...data.model, id: 'second', name: '同模型的另一方案' }]
  useModelConfigStore().models = models
  await page()
  expect(document.querySelectorAll('.catalog-model-row')).toHaveLength(2)
  await click('启用供应商连接 ' + data.provider.name)
  expect(models.every((item) => item.enabled)).toBe(true)
  expect(document.body.textContent).toContain('连接已停用')
  expect(useModelConfigStore().selected?.model_configuration_id).toBe(data.model.id)
  expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'PATCH')).toHaveLength(1)
})

it('切换多份连接只读取各自模型，关闭有草稿的弹窗需确认并保留秘密输入直到卸载', async () => {
  connections.push({ ...data.provider, id: 'other', name: '另一个账号' })
  models = [data.model]
  useModelConfigStore().models = models
  const onClose = vi.fn<() => void>()
  const { wrapper } = await page(false, onClose)
  await click('切换连接 另一个账号')
  expect(document.body.textContent).not.toContain(data.model.name)
  document
    .querySelector<HTMLButtonElement>(
      '.provider-connection-card.is-selected [aria-label="编辑供应商"]',
    )!
    .click()
  await flushPromises()
  const secret = document.querySelector<HTMLInputElement>('[name="api_key"]')!
  secret.value = '仅留在表单内存'
  secret.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
  await click('关闭')
  expect(document.body.textContent).toContain('放弃未保存的更改？')
  await click('继续编辑')
  expect(secret.value).toBe('仅留在表单内存')
  expect(onClose).not.toHaveBeenCalled()
  await click('关闭')
  await click('放弃更改')
  expect(onClose).not.toHaveBeenCalled()
  expect(document.querySelectorAll('[role="dialog"]')).toHaveLength(1)
  expect(document.querySelector('[name="api_key"]')).toBeNull()
  await click('关闭')
  expect(onClose).toHaveBeenCalledTimes(1)
  wrapper.unmount()
  expect(document.querySelector('[name="api_key"]')).toBeNull()
})

it('高级设置以独立居中弹窗打开，无模型选择下拉，脏草稿离页可取消', async () => {
  models = [data.model]
  useModelConfigStore().models = models
  const { router } = await page()
  await click('高级设置')
  expect(document.querySelectorAll('[role="dialog"]')).toHaveLength(2)
  expect(document.querySelector('.config-modal--editor')).not.toBeNull()
  expect(document.querySelector('.config-modal--drawer')).toBeNull()
  expect(document.querySelector('[name="catalog_model_id"]')).toBeNull()
  const name = document.querySelector<HTMLInputElement>('[name="name"]')!
  name.value = '草稿'
  name.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
  const leaving = router.push('/other')
  await flushPromises()
  await click('继续编辑')
  await leaving
  expect(router.currentRoute.value.path).toBe('/')
  expect(name.value).toBe('草稿')
})

it('写入成功但快照刷新失败时明确提示已保存，刷新确认不会再次提交启停', async () => {
  models = [data.model]
  useModelConfigStore().models = models
  await page()
  fetchMock.mockResolvedValueOnce(response({ ...data.model, enabled: false, version: 2 }))
  fetchMock.mockResolvedValueOnce(response(null, 500, 50000, '快照服务暂不可用'))
  await click(`启用模型 ${data.model.name}`)
  expect(document.body.textContent).toContain('启停已保存')
  expect(document.body.textContent).toContain('请刷新确认')
  expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'PATCH')).toHaveLength(1)
})

it('连接切换取消旧目录请求，迟到的旧目录和卸载后的结果不能覆盖当前列表', async () => {
  connections.push({ ...data.provider, id: 'other', name: '另一个账号' })
  const pending = deferredResponse()
  fetchMock.mockReturnValueOnce(pending.promise)
  const { wrapper } = await page()
  const signal = fetchMock.mock.lastCall?.[1]?.signal
  await click('切换连接 另一个账号')
  expect(signal?.aborted).toBe(true)
  pending.resolve(response([{ ...data.catalog, display_name: '迟到的旧目录' }]))
  await flushPromises()
  expect(document.body.textContent).not.toContain('迟到的旧目录')
  expect(document.body.textContent).toContain(data.catalog.display_name)
  wrapper.unmount()
  expect(document.querySelectorAll('[role="dialog"]')).toHaveLength(0)
})

it('初次配置取消只关闭编辑弹窗，供应商面板仍可重新添加连接', async () => {
  connections = []
  useModelConfigStore().configurations = []
  const onClose = vi.fn<() => void>()
  await page(false, onClose)
  const trigger = [...document.querySelectorAll<HTMLButtonElement>('button')].find(
    (button) => button.textContent?.trim() === '添加连接',
  )!
  await click('添加连接')
  await click('取消')
  await vi.waitFor(() => expect(document.activeElement).toBe(trigger))
  expect(onClose).not.toHaveBeenCalled()
  expect(document.querySelectorAll('[role="dialog"]')).toHaveLength(1)
  expect(document.querySelector('[name="api_key"]')).toBeNull()
  await click('添加连接')
  expect(document.querySelector('[name="api_key"]')).not.toBeNull()
})

it('未改动的高级设置保存期间同样禁止关闭和主动离页', async () => {
  models = [data.model]
  useModelConfigStore().models = models
  const { router } = await page()
  await click('高级设置')
  const pending = deferredResponse()
  fetchMock.mockReturnValueOnce(pending.promise)
  await click('保存配置')
  expect(document.querySelector<HTMLButtonElement>('[aria-label="关闭"]')!.disabled).toBe(true)
  await router.push('/other')
  expect(router.currentRoute.value.path).toBe('/')
  pending.resolve(response({ ...data.model, version: 2 }))
  await flushPromises()
  expect(document.querySelector('[name="name"]')).toBeNull()
})

it('启停期间退出账号仍允许离开，取消与迟到响应不能恢复旧账号缓存', async () => {
  models = [data.model]
  useModelConfigStore().models = models
  const { router } = await page()
  const pending = deferredResponse()
  fetchMock.mockReturnValueOnce(pending.promise)
  await click(`启用模型 ${data.model.name}`)
  useAuthStore().logout()
  await router.push('/other')
  expect(router.currentRoute.value.path).toBe('/other')
  pending.resolve(response({ ...data.model, enabled: false, version: 2 }))
  await flushPromises()
  expect(useModelConfigStore().models).toEqual([])
  expect(document.querySelector('[role="dialog"]')).toBeNull()
})

// 非当前连接可以独立启停，不能顺带切换模型目录或改变其他连接的模型。
it('连接卡片独立启停非当前连接，编辑弹窗关闭时保护草稿再切换连接', async () => {
  connections.push({ ...data.provider, id: 'other', name: '备用账号' })
  models = [
    data.model,
    { ...data.model, id: 'other-model', name: '备用模型', provider_configuration_id: 'other' },
  ]
  useModelConfigStore().models = models
  await page()
  expect(document.querySelectorAll('.provider-connection-card')).toHaveLength(2)
  await click('启用供应商连接 备用账号')
  expect(connections.find((item) => item.id === 'other')?.enabled).toBe(false)
  expect(connections[0]?.enabled).toBe(true)
  expect(models.every((item) => item.enabled)).toBe(true)
  expect(document.querySelector('.provider-connection-card.is-selected')?.textContent).toContain(
    data.provider.name,
  )
  expect(document.querySelector('.provider-models')?.textContent).toContain(data.model.name)
  await click('切换连接 备用账号')
  expect(document.querySelector('.provider-models')?.textContent).toContain('备用模型')
  expect(document.querySelector('.provider-models')?.textContent).not.toContain(data.model.name)
  document
    .querySelector<HTMLButtonElement>(
      '.provider-connection-card.is-selected [aria-label="编辑供应商"]',
    )!
    .click()
  await flushPromises()
  const secret = document.querySelector<HTMLInputElement>('[name="api_key"]')!
  secret.value = '切换前保留的密钥草稿'
  secret.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
  await click('关闭')
  await click('继续编辑')
  expect(secret.value).toBe('切换前保留的密钥草稿')
  expect(document.querySelector('.provider-connection-card.is-selected')?.textContent).toContain(
    '备用账号',
  )
  await click('关闭')
  await click('放弃更改')
  expect(document.querySelector('[name="api_key"]')).toBeNull()
  await click('切换连接 ' + data.provider.name)
  expect(document.querySelector('.provider-models')?.textContent).toContain(data.model.name)
})

// 所有连接都有直接操作，引用校验必须以被删除的连接为准。
it('删除非当前连接时仍保护其关联模型，不发送删除请求', async () => {
  connections.push({ ...data.provider, id: 'other', name: '备用账号' })
  models = [{ ...data.model, provider_configuration_id: 'other' }]
  useModelConfigStore().models = models
  await page()
  document
    .querySelector<HTMLButtonElement>(
      '[aria-label="供应商连接：备用账号"] [aria-label="删除供应商"]',
    )!
    .click()
  await flushPromises()
  expect(document.querySelector('[role="alert"]')?.textContent).toContain('仍被引用')
  expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(false)
  expect(document.querySelector('.provider-connection-card.is-selected')?.textContent).toContain(
    data.provider.name,
  )
})

// 直接编辑另一张卡片会先选择其连接，表单不得沿用原连接的名称或密钥。
it('直接编辑另一份连接时定位对应表单且不回显已保存密钥', async () => {
  connections.push({ ...data.provider, id: 'other', name: '备用账号' })
  models = [data.model]
  useModelConfigStore().models = models
  await page()
  document
    .querySelector<HTMLButtonElement>(
      '[aria-label="供应商连接：备用账号"] [aria-label="编辑供应商"]',
    )!
    .click()
  await flushPromises()
  expect(document.querySelector('.provider-connection-card.is-selected')?.textContent).toContain(
    '备用账号',
  )
  expect(document.querySelector<HTMLInputElement>('[name="name"]')?.value).toBe('备用账号')
  expect(document.querySelector<HTMLInputElement>('[name="api_key"]')?.value).toBe('')
  expect(document.querySelector('.provider-models')?.textContent).not.toContain(data.model.name)
})

// 直接测试沿用服务端结果与统一执行锁，不增加确认层，也不能误触默认写入。
it('点击测试立即请求，重复点击只测一次，失败后可直接重试并显示结果', async () => {
  models = [data.model]
  useModelConfigStore().models = models
  await page()
  const pending = deferredResponse()
  fetchMock.mockReturnValueOnce(pending.promise)
  await click('测试')
  await click('测试')
  expect(document.querySelectorAll('[role="dialog"]')).toHaveLength(1)
  expect(document.body.textContent).toContain('正在测试文本流')
  expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/test'))).toHaveLength(1)
  pending.resolve(response(null, 500, 50000, '测试连接暂时失败'))
  await flushPromises()
  expect(document.querySelector('.catalog-test-feedback')?.textContent).toContain(
    '测试连接暂时失败',
  )
  fetchMock.mockResolvedValueOnce(
    response({
      latency_ms: 42,
      model_version: 1,
      provider_configuration_version: 1,
      verified: 'streaming_text',
    }),
  )
  await click('测试')
  expect(document.querySelector('.catalog-test-feedback')?.textContent).toContain('文本流通过')
  expect(document.body.textContent).not.toContain('测试已结束，请查看模型测试结果。')
  expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/test'))).toHaveLength(2)
  expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'PUT')).toBe(false)
})

it('清除默认点击即保存，不打开确认层且等待期间禁止重复操作', async () => {
  models = [data.model]
  useModelConfigStore().models = models
  await page()
  const pending = deferredResponse()
  fetchMock.mockReturnValueOnce(pending.promise)
  await click('清除默认')
  await click('清除默认')
  expect(document.querySelectorAll('[role="dialog"]')).toHaveLength(1)
  expect(fetchMock.mock.calls.filter(([, options]) => options?.method === 'PUT')).toHaveLength(1)
  pending.resolve(
    response({ ...data.selected, model_configuration_id: null, model: null, version: 2 }),
  )
  await flushPromises()
  expect(document.querySelector('.catalog-model-row')?.textContent).not.toContain('当前默认')
})

it('点击空连接卡片打开同一添加表单，取消后焦点回到卡片且可以再次添加', async () => {
  connections = []
  useModelConfigStore().configurations = []
  await page()
  const card = document.querySelector<HTMLButtonElement>('.provider-connection-empty')!
  expect(card.tagName).toBe('BUTTON')
  await click('添加首个供应商连接')
  expect(document.querySelectorAll('[role="dialog"]')).toHaveLength(2)
  expect(document.querySelector<HTMLInputElement>('[name="name"]')?.value).toBe(
    data.brand.display_name,
  )
  expect(card.disabled).toBe(true)
  await click('取消')
  await vi.waitFor(() => expect(document.activeElement).toBe(card))
  expect(card.disabled).toBe(false)
  await click('添加首个供应商连接')
  expect(document.querySelectorAll('[role="dialog"]')).toHaveLength(2)
})
