/** 配置 API 与表单规则：验证认证、版本请求、密钥边界、错误分类和目录预算规则。 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createTestPinia } from '@tests/support/vitest/mount'
import { authenticate } from '@tests/support/vitest/auth'
import { response } from '@tests/support/vitest/http'
import { bailianConfigData, modelConfigData } from '@tests/support/data/model-config'
import { useAuthStore } from '@/features/auth/store'
import * as api from '../api'
import { validateModel, validateProvider } from '../validation'

const fetchMock = vi.fn<typeof fetch>()
// 每例使用真实认证状态，网络只在 HTTP 边界替换。
beforeEach(async () => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
  await authenticate(createTestPinia(), fetchMock)
})

describe('模型配置协议', () => {
  it('百炼响应解码完整地址，丢弃凭据并拒绝混用地域字段的响应', () => {
    const { provider } = bailianConfigData()
    expect(api.decodeConfiguration({ ...provider, api_key: '不能缓存' })).toEqual(provider)
    for (const endpoint of [
      {},
      { base_url: '' },
      { ...provider.endpoint_config, endpoint_id: 'cn-beijing' },
    ])
      expect(() => api.decodeConfiguration({ ...provider, endpoint_config: endpoint })).toThrow(
        '响应格式无效',
      )
  })
  it('带 Bearer 与版本写入、按协议读取目录并拒绝损坏的响应', async () => {
    const { provider, catalog } = modelConfigData(),
      signal = new AbortController().signal
    fetchMock.mockResolvedValueOnce(response({ ...provider, api_key: '不得缓存的字段' }))
    const result = await api.patchProvider(provider.id, { version: 1, name: '新名称' }, signal)
    expect(result).not.toHaveProperty('api_key')
    const [url, options] = fetchMock.mock.calls[0]!
    expect(url).toBe('/api/model-config/provider-configurations/provider-one')
    expect(new Headers(options?.headers).get('Authorization')).toBe('Bearer test-access-token')
    expect(JSON.parse(String(options?.body))).toEqual({ version: 1, name: '新名称' })
    fetchMock.mockResolvedValueOnce(response([catalog]))
    await api.loadCatalog('anthropic', 'messages', signal)
    expect(String(fetchMock.mock.calls[1]![0])).toContain('provider=anthropic&api_format=messages')
    fetchMock.mockResolvedValueOnce(response({ ...provider, version: 0 }))
    await expect(
      api.createProvider(
        {
          name: '连接',
          provider: 'anthropic',
          api_format: 'messages',
          endpoint_config: { endpoint_id: 'official' },
          api_key: 'secret',
        },
        signal,
      ),
    ).rejects.toThrow('响应格式无效')
  })
  it('上游鉴权业务失败保持登录，只有 API HTTP 401 使当前身份失效', async () => {
    fetchMock.mockResolvedValueOnce(response(null, 200, 20002, '模型服务鉴权失败'))
    await expect(api.testModel('m', new AbortController().signal)).rejects.toMatchObject({
      code: 20002,
    })
    expect(useAuthStore().isAuthenticated).toBe(true)
    fetchMock.mockResolvedValueOnce(response(null, 401, 40101, '登录过期'))
    await expect(api.getDefault(new AbortController().signal)).rejects.toMatchObject({
      status: 401,
    })
    expect(useAuthStore().isAuthenticated).toBe(false)
  })
  it('检查默认概要归属、测试延迟和嵌套能力，并按版本删除', async () => {
    const { selected, catalog } = modelConfigData(),
      signal = new AbortController().signal
    expect(() => api.decodeDefault({ ...selected, model_configuration_id: 'other' })).toThrow(
      '响应格式无效',
    )
    expect(() =>
      api.decodeCatalog({
        ...catalog,
        reasoning: { ...catalog.reasoning, budget: { min: 2, max: 1 } },
      }),
    ).toThrow('响应格式无效')
    fetchMock.mockResolvedValueOnce(
      response({
        latency_ms: -1,
        model_version: 1,
        provider_configuration_version: 1,
        verified: 'streaming_text',
      }),
    )
    await expect(api.testModel('m', signal)).rejects.toThrow('响应格式无效')
    fetchMock.mockResolvedValueOnce(response(null))
    await api.deleteModel('model/id', 3, signal)
    expect(fetchMock.mock.calls[1]![0]).toBe('/api/model-config/models/model%2Fid?version=3')
  })
})

describe('目录驱动表单校验', () => {
  it('百炼只需完整官方兼容地址，无需地域，原生地址和不安全目标均提示修改', () => {
    const { provider, brand } = bailianConfigData()
    const body = { ...provider, api_key: '' }
    expect(validateProvider(body, brand, true)).toEqual({})
    expect(
      validateProvider(
        { ...body, endpoint_config: { base_url: `  ${provider.endpoint_config.base_url}/  ` } },
        brand,
        true,
      ),
    ).toEqual({})
    for (const base_url of [
      '',
      'https://ws-demo.cn-beijing.maas.aliyuncs.com/api/v1',
      'https://evil.invalid/compatible-mode/v1',
      'http://dashscope.aliyuncs.com/compatible-mode/v1',
      'https://dashscope.aliyuncs.com/compatible-mode/v1?key=secret',
    ])
      expect(
        validateProvider({ ...body, endpoint_config: { base_url } }, brand, true).base_url,
      ).toContain('OpenAI 兼容地址')
  })
  it('校验手动及模型默认预算与输出上限，禁止小数和未知模式', () => {
    const { model, catalog } = modelConfigData()
    expect(validateModel(model, catalog)).toEqual({})
    expect(validateModel({ ...model, max_output_tokens: 4096 }, catalog).reasoning).toContain(
      '必须小于',
    )
    expect(
      validateModel({ ...model, reasoning: { mode: 'budget', budget_tokens: 1023 } }, catalog)
        .reasoning,
    ).toBeTruthy()
    expect(
      validateModel({ ...model, max_output_tokens: 2.5 }, catalog).max_output_tokens,
    ).toBeTruthy()
    expect(
      validateModel({ ...model, reasoning: { mode: 'effort', effort: 'invented' } }, catalog)
        .reasoning,
    ).toBeTruthy()
    expect(validateModel(model, undefined).catalog_model_id).toBeTruthy()
    expect(
      validateModel(model, {
        ...catalog,
        reasoning: { ...catalog.reasoning, allowed_modes: ['off'], default: { mode: 'off' } },
      }),
    ).toEqual({})
  })
  it('供应商编辑允许留空密钥，端点和业务空间仍需符合目录', () => {
    const { brand } = modelConfigData()
    const body = {
      name: '测试',
      provider: brand.provider,
      api_format: brand.default_api_format,
      api_key: '',
      endpoint_config: { endpoint_id: 'official' },
    }
    expect(validateProvider(body, brand, true)).toEqual({})
    expect(validateProvider(body, brand, false).api_key).toBeTruthy()
    const regional = {
      ...brand,
      endpoints: [
        { endpoint_id: 'cn-hongkong', display_name: '香港', workspace_id_required: true },
      ],
    }
    expect(
      validateProvider({ ...body, endpoint_config: { endpoint_id: 'cn-hongkong' } }, regional, true)
        .workspace,
    ).toBeTruthy()
    expect(
      validateProvider(
        { ...body, endpoint_config: { endpoint_id: 'cn-hongkong', workspace_id: 'https://url' } },
        regional,
        true,
      ).workspace,
    ).toBeTruthy()
  })
})
