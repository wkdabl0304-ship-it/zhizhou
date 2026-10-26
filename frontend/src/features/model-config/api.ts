/** 模型配置 HTTP 边界：复用认证和统一信封，验证公开字段后才允许数据进入表单和状态。 */
import { ApiError, authenticatedFetch, readEnvelope } from '@/features/auth/authenticated'
import type {
  ApiFormat,
  CatalogModel,
  DefaultModel,
  ModelConfiguration,
  ModelInput,
  ModelPatch,
  Provider,
  ProviderConfiguration,
  ProviderInfo,
  ProviderInput,
  ProviderPatch,
  Reasoning,
  TestResult,
} from './types'

const prefix = '/api/model-config'
const providers = ['openai', 'anthropic', 'deepseek', 'bailian']
const formats = ['responses', 'chat_completions', 'messages']
const modes = ['default', 'off', 'effort', 'budget']
/** 拒绝无效响应，避免损坏的版本、参数和引用进入后续写请求。 */
function requireValue(value: unknown): asserts value {
  if (!value) throw new ApiError('模型配置响应格式无效')
}
/** 验证 JSON 对象，排除数组和空值。 */
function object(value: unknown): Record<string, unknown> {
  requireValue(value && typeof value === 'object' && !Array.isArray(value))
  return value as Record<string, unknown>
}
/** 判断非空文本。 */
function text(value: unknown): value is string {
  return typeof value === 'string' && !!value.trim()
}
/** 判断正整数版本或 token 上限。 */
function positive(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0
}
/** 判断由纯字符串构成的目录选项。 */
function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(text)
}
/** 校验受限的推理联合类型。 */
function reasoning(value: unknown): Reasoning {
  const row = object(value)
  requireValue(
    modes.includes(String(row.mode)) &&
      (row.mode !== 'effort' || text(row.effort)) &&
      (row.mode !== 'budget' || positive(row.budget_tokens)),
  )
  return value as Reasoning
}
/** 验证公开模型目录，包括预算上下限和格式能力。 */
export function decodeCatalog(value: unknown): CatalogModel {
  const row = object(value),
    control = object(row.reasoning),
    capabilities = object(row.capabilities)
  requireValue(
    text(row.catalog_model_id) &&
      providers.includes(String(row.provider)) &&
      text(row.model_id) &&
      text(row.display_name) &&
      strings(row.supported_api_formats) &&
      row.supported_api_formats.every((item) => formats.includes(item)) &&
      typeof row.available === 'boolean' &&
      positive(row.max_output_tokens) &&
      typeof capabilities.streaming === 'boolean' &&
      typeof capabilities.tool_calling === 'boolean',
  )
  requireValue(
    strings(control.allowed_modes) &&
      control.allowed_modes.every((item) => modes.includes(item)) &&
      strings(control.effort_options) &&
      typeof control.budget_must_fit_output === 'boolean',
  )
  reasoning(control.default)
  if (control.budget !== null) {
    const budget = object(control.budget)
    requireValue(positive(budget.min) && positive(budget.max) && budget.max >= budget.min)
  }
  requireValue(
    typeof row.verified_at === 'string' &&
      Object.values(object(row.format_constraints)).every((item) => typeof item === 'string'),
  )
  return value as CatalogModel
}
/** 校验供应商目录，不在前端维护品牌和端点策略的副本。 */
function decodeProvider(value: unknown): ProviderInfo {
  const row = object(value)
  requireValue(
    providers.includes(String(row.provider)) &&
      text(row.display_name) &&
      strings(row.api_formats) &&
      row.api_formats.every((item) => formats.includes(item)) &&
      row.api_formats.includes(String(row.default_api_format)) &&
      typeof row.recommended === 'boolean' &&
      strings(row.provider_configuration_fields),
  )
  requireValue(Array.isArray(row.endpoints) && row.endpoints.length)
  for (const item of row.endpoints) {
    const endpoint = object(item)
    requireValue(
      text(endpoint.endpoint_id) &&
        text(endpoint.display_name) &&
        typeof endpoint.workspace_id_required === 'boolean',
    )
  }
  return value as ProviderInfo
}
/** 校验实体的身份、版本与时间字段。 */
function entity(value: unknown) {
  const row = object(value)
  requireValue(
    text(row.id) &&
      text(row.name) &&
      positive(row.version) &&
      text(row.created_at) &&
      Number.isFinite(Date.parse(row.created_at)) &&
      text(row.updated_at) &&
      Number.isFinite(Date.parse(row.updated_at)),
  )
  return row
}
/** 解码安全供应商配置，返回值不复制响应中的未知字段或凭据。 */
export function decodeConfiguration(value: unknown): ProviderConfiguration {
  const row = entity(value),
    endpoint = object(row.endpoint_config)
  requireValue(
    providers.includes(String(row.provider)) &&
      formats.includes(String(row.api_format)) &&
      typeof row.api_key_configured === 'boolean' &&
      (row.provider === 'bailian'
        ? text(endpoint.base_url) && endpoint.endpoint_id == null && endpoint.workspace_id == null
        : text(endpoint.endpoint_id) && endpoint.base_url == null && endpoint.workspace_id == null),
  )
  return {
    id: row.id as string,
    name: row.name as string,
    provider: row.provider as Provider,
    api_format: row.api_format as ApiFormat,
    endpoint_config:
      row.provider === 'bailian'
        ? { base_url: endpoint.base_url as string }
        : { endpoint_id: endpoint.endpoint_id as string },
    api_key_configured: row.api_key_configured as boolean,
    version: row.version as number,
    created_at: row.created_at as string,
    updated_at: row.updated_at as string,
  }
}
/** 解码模型方案，目录失效仍可读取和删除。 */
export function decodeModel(value: unknown): ModelConfiguration {
  const row = entity(value)
  requireValue(
    text(row.provider_configuration_id) &&
      text(row.catalog_model_id) &&
      positive(row.max_output_tokens) &&
      typeof row.available === 'boolean',
  )
  return {
    id: row.id as string,
    name: row.name as string,
    version: row.version as number,
    created_at: row.created_at as string,
    updated_at: row.updated_at as string,
    provider_configuration_id: row.provider_configuration_id as string,
    catalog_model_id: row.catalog_model_id as string,
    reasoning: reasoning(row.reasoning),
    max_output_tokens: row.max_output_tokens as number,
    available: row.available as boolean,
    catalog: row.catalog === null ? null : decodeCatalog(row.catalog),
  }
}
/** 解码默认引用并核对概要归属。 */
export function decodeDefault(value: unknown): DefaultModel {
  const row = object(value)
  requireValue(
    positive(row.version) &&
      text(row.updated_at) &&
      Number.isFinite(Date.parse(row.updated_at)) &&
      (row.model_configuration_id === null || text(row.model_configuration_id)),
  )
  const model = row.model === null ? null : decodeModel(row.model)
  requireValue(
    row.model_configuration_id === null ? model === null : model?.id === row.model_configuration_id,
  )
  return {
    model_configuration_id: row.model_configuration_id as string | null,
    version: row.version as number,
    updated_at: row.updated_at as string,
    model,
  }
}
/** 验证文本流测试结果，不把工具能力或默认状态混入测试结论。 */
function decodeTest(value: unknown): TestResult {
  const row = object(value)
  requireValue(
    typeof row.latency_ms === 'number' &&
      Number.isFinite(row.latency_ms) &&
      row.latency_ms >= 0 &&
      positive(row.provider_configuration_version) &&
      positive(row.model_version) &&
      row.verified === 'streaming_text',
  )
  return value as TestResult
}
/** 发送可取消的 JSON 请求，只将 API 真正的 HTTP 401 交给认证模块。 */
async function request(path: string, signal: AbortSignal, method = 'GET', body?: unknown) {
  return readEnvelope(
    await authenticatedFetch(`${prefix}${path}`, {
      method,
      signal,
      headers: {
        Accept: 'application/json',
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    }),
  )
}
/** 校验列表中的每一项，拒绝只验证数组外壳的损坏响应。 */
function list<T>(value: unknown, decode: (item: unknown) => T): T[] {
  requireValue(Array.isArray(value))
  return value.map(decode)
}
/** 读取模型管理的目录、配置与默认引用。 */
export async function loadManagement(signal: AbortSignal) {
  const [brands, configurations, models, selected] = await Promise.all([
    request('/catalog/providers', signal),
    request('/provider-configurations', signal),
    request('/models', signal),
    request('/default', signal),
  ])
  return {
    brands: list(brands, decodeProvider),
    configurations: list(configurations, decodeConfiguration),
    models: list(models, decodeModel),
    selected: decodeDefault(selected),
  }
}
/** 读取针对所选供应商及协议计算的目录，防止使用未按协议裁剪的推理选项。 */
export async function loadCatalog(provider: Provider, format: ApiFormat, signal: AbortSignal) {
  return list(
    await request(
      `/catalog/models?${new URLSearchParams({ provider, api_format: format })}`,
      signal,
    ),
    decodeCatalog,
  )
}
/** 读取全局默认供聊天页展示。 */
export async function getDefault(signal: AbortSignal) {
  return decodeDefault(await request('/default', signal))
}
/** 创建供应商；密钥仅出现在本次写请求中。 */
export async function createProvider(body: ProviderInput, signal: AbortSignal) {
  return decodeConfiguration(await request('/provider-configurations', signal, 'POST', body))
}
/** 按读取版本修改供应商，空白密钥应由表单省略。 */
export async function patchProvider(id: string, body: ProviderPatch, signal: AbortSignal) {
  return decodeConfiguration(
    await request(`/provider-configurations/${encodeURIComponent(id)}`, signal, 'PATCH', body),
  )
}
/** 按版本删除没有关联方案的供应商。 */
export async function deleteProvider(id: string, version: number, signal: AbortSignal) {
  requireValue(
    (await request(
      `/provider-configurations/${encodeURIComponent(id)}?version=${version}`,
      signal,
      'DELETE',
    )) === null,
  )
}
/** 创建可复用模型方案。 */
export async function createModel(body: ModelInput, signal: AbortSignal) {
  return decodeModel(await request('/models', signal, 'POST', body))
}
/** 按读取版本修改方案，供应商归属不可改变。 */
export async function patchModel(id: string, body: ModelPatch, signal: AbortSignal) {
  return decodeModel(await request(`/models/${encodeURIComponent(id)}`, signal, 'PATCH', body))
}
/** 按版本删除非默认方案。 */
export async function deleteModel(id: string, version: number, signal: AbortSignal) {
  requireValue(
    (await request(`/models/${encodeURIComponent(id)}?version=${version}`, signal, 'DELETE')) ===
      null,
  )
}
/** 切换或清除全局默认，明确的 null 是该接口的合法操作。 */
export async function putDefault(id: string | null, version: number, signal: AbortSignal) {
  return decodeDefault(
    await request('/default', signal, 'PUT', { version, model_configuration_id: id }),
  )
}
/** 主动测试已保存的模型，不隐式设置默认。 */
export async function testModel(id: string, signal: AbortSignal) {
  return decodeTest(await request(`/models/${encodeURIComponent(id)}/test`, signal, 'POST'))
}
