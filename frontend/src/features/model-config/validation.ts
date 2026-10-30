/** 模型表单规则与展示标签：能力取自服务端目录，前端仅校验可立即反馈的字段边界。 */
import type { CatalogModel, ModelInput, ProviderInfo, ProviderInput, Reasoning } from './types'
import { decodePolicy, validateSelection } from '@/features/model-selection/contract'
export const formatLabels = {
  responses: 'Responses',
  chat_completions: 'Chat Completions',
  messages: 'Messages',
}
export const modeLabels = {
  default: '模型默认',
  off: '关闭思考',
  effort: '推理档位',
  budget: '思考预算',
}
export const effortLabels: Record<string, string> = {
  low: '低',
  medium: '中',
  high: '高',
  xhigh: '很高',
  max: '最高',
}
/** 清除用户粘贴 Base URL 时附带的首尾空白与末尾斜杠。 */
export function normalizeBaseUrl(value: string): string {
  return value.trim().replace(/\/+$/, '')
}
/** 返回供应商的字段错误，编辑时允许省略密钥。 */
export function validateProvider(
  body: ProviderInput,
  brand: ProviderInfo | undefined,
  editing: boolean,
) {
  const errors: Record<string, string> = {}
  if (!body.name.trim() || Array.from(body.name.trim()).length > 100)
    errors.name = '请填写 1–100 字符的配置名称'
  if (!brand || !brand.api_formats.includes(body.api_format))
    errors.api_format = '请选择供应商支持的接口格式'
  const endpoint = brand?.endpoints.find(
    (item) => item.endpoint_id === body.endpoint_config.endpoint_id,
  )
  if (body.provider === 'bailian') {
    // 只做可立即反馈的官方兼容地址检查；服务端在保存及每轮快照时再次校验。
    const address = normalizeBaseUrl(body.endpoint_config.base_url ?? '')
    if (
      !/^https:\/\/(?:dashscope(?:-intl)?\.aliyuncs\.com|[a-z0-9][a-z0-9_-]{0,63}\.[a-z][a-z0-9-]{0,62}\.maas\.aliyuncs\.com)\/compatible-mode\/v1$/.test(
        address,
      )
    )
      errors.base_url =
        '请粘贴百炼控制台的 OpenAI 兼容地址，需以 https:// 开头、/compatible-mode/v1 结尾'
  } else if (!endpoint) errors.endpoint = '请选择有效的官方端点'
  const workspace = body.endpoint_config.workspace_id
  if (endpoint?.workspace_id_required && !workspace?.trim())
    errors.workspace = '该地域需要填写业务空间 ID'
  else if (workspace && !/^[A-Za-z0-9_-]{1,64}$/.test(workspace))
    errors.workspace = '使用 1–64 位字母、数字、下划线或连字符'
  if (!editing && !body.api_key.trim()) errors.api_key = '请输入 API Key'
  return errors
}
/** 返回模型方案的字段错误，包括应用默认思考预算与输出上限的关联。 */
export function validateModel(body: ModelInput, spec: CatalogModel | undefined) {
  const errors: Record<string, string> = {}
  if (!body.name.trim() || Array.from(body.name.trim()).length > 100)
    errors.name = '请填写 1–100 字符的方案名称'
  if (!spec?.available) errors.catalog_model_id = '请选择当前可用的目录模型'
  if (!spec) return errors
  if (
    !Number.isSafeInteger(body.max_output_tokens) ||
    body.max_output_tokens < 1 ||
    body.max_output_tokens > spec.max_output_tokens
  )
    errors.max_output_tokens = `请填写 1–${spec.max_output_tokens.toLocaleString()} 的整数`
  const selected = body.reasoning.mode === 'default' ? spec.reasoning.default : body.reasoning
  if (body.reasoning_policy?.mode === 'selectable') {
    try {
      const policy = decodePolicy(body.reasoning_policy)
      if (policy.mode === 'selectable') {
        if (
          policy.allowed_modes.some((mode) => !spec.reasoning.allowed_modes.includes(mode)) ||
          policy.effort_options.some((effort) => !spec.reasoning.effort_options.includes(effort))
        )
          throw new Error('范围超出目录能力')
        if (
          policy.budget &&
          (!spec.reasoning.budget ||
            policy.budget.min < spec.reasoning.budget.min ||
            policy.budget.max > spec.reasoning.budget.max ||
            (spec.reasoning.budget_must_fit_output && policy.budget.max >= body.max_output_tokens))
        )
          throw new Error('预算范围须符合目录并小于输出上限')
        if (
          selected.mode === 'default' ||
          validateSelection(
            { model_configuration_id: 'draft', reasoning: selected },
            {
              model_configuration_id: 'draft',
              name: body.name,
              catalog_model_id: body.catalog_model_id,
              display_name: spec.display_name,
              reasoning_control: { ...policy, default: selected },
            },
          )
        )
          throw new Error('默认推理值必须在允许范围内')
      }
    } catch (failure) {
      errors.reasoning_policy =
        failure instanceof Error && !failure.message.includes('响应')
          ? failure.message
          : '请至少选择一个允许的推理强度，并填写有效的预算范围'
    }
  }
  // 后端先解析 default 再校验实际模式，旧方案的默认引用也遵循相同规则。
  if (!spec.reasoning.allowed_modes.includes(selected.mode))
    errors.reasoning = '请选择模型支持的推理方式'
  if (selected.mode === 'effort' && !spec.reasoning.effort_options.includes(selected.effort))
    errors.reasoning = '请选择模型支持的推理档位'
  if (selected.mode === 'budget') {
    const limits = spec.reasoning.budget
    if (
      !limits ||
      !Number.isSafeInteger(selected.budget_tokens) ||
      selected.budget_tokens < limits.min ||
      selected.budget_tokens > limits.max
    )
      errors.reasoning = '思考预算必须是目录范围内的整数'
    else if (
      spec.reasoning.budget_must_fit_output &&
      selected.budget_tokens >= body.max_output_tokens
    )
      errors.reasoning = '思考预算必须小于最大输出 tokens'
  }
  return errors
}
/** 描述方案推理设置，保留未知原生档位的原文。 */
export function describeReasoning(value: Reasoning): string {
  return value.mode === 'effort'
    ? `推理 · ${effortLabels[value.effort] ?? value.effort}`
    : value.mode === 'budget'
      ? `思考预算 · ${value.budget_tokens.toLocaleString()}`
      : modeLabels[value.mode]
}
