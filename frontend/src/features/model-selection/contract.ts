/** 选择接口与策略的纯校验：确保聊天只提交后端开放的具体值，管理策略复用同一契约。 */
import { ApiError } from '@/features/auth/authenticated'
import type {
  ConcreteReasoning,
  ModelOptions,
  ModelSelection,
  ReasoningPolicy,
  SelectableModel,
  SelectionFields,
  SelectionIssue,
} from './types'

/** 拒绝损坏的允许范围，不将格式错误解释成无可用模型。 */
function requireValue(value: unknown): asserts value {
  if (!value) throw new ApiError('模型选择响应格式无效')
}
/** 检查未知值是否为非数组 JSON 对象。 */
function object(value: unknown): Record<string, unknown> {
  requireValue(value && typeof value === 'object' && !Array.isArray(value))
  return value as Record<string, unknown>
}
/** 判断非空字符串字段。 */
function text(value: unknown): value is string {
  return typeof value === 'string' && !!value.trim()
}
/** 判断正整数预算或版本。 */
function positive(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0
}
/** 读取具体推理分支，明确排除管理端的 default 和混合参数。 */
export function decodeReasoning(value: unknown): ConcreteReasoning {
  const row = object(value)
  requireValue(
    row.mode === 'off' ||
      (row.mode === 'effort' && text(row.effort)) ||
      (row.mode === 'budget' && positive(row.budget_tokens)),
  )
  requireValue(
    Object.keys(row).every(
      (key) =>
        key === 'mode' ||
        key ===
          (row.mode === 'effort' ? 'effort' : row.mode === 'budget' ? 'budget_tokens' : 'mode'),
    ),
  )
  return row.mode === 'off'
    ? { mode: 'off' }
    : row.mode === 'effort'
      ? { mode: 'effort', effort: row.effort as string }
      : { mode: 'budget', budget_tokens: row.budget_tokens as number }
}
/** 解码固定或受限策略，数组顺序保持后端原样。 */
export function decodePolicy(value: unknown): ReasoningPolicy {
  const row = object(value)
  if (row.mode === 'fixed') return { mode: 'fixed' }
  requireValue(
    row.mode === 'selectable' &&
      Array.isArray(row.allowed_modes) &&
      row.allowed_modes.length &&
      row.allowed_modes.every((mode) => ['off', 'effort', 'budget'].includes(String(mode))) &&
      new Set(row.allowed_modes).size === row.allowed_modes.length,
  )
  requireValue(
    Array.isArray(row.effort_options) &&
      row.effort_options.every(text) &&
      new Set(row.effort_options).size === row.effort_options.length,
  )
  requireValue(row.allowed_modes.includes('effort') === !!row.effort_options.length)
  let budget = null
  if (row.budget !== null) {
    const range = object(row.budget)
    requireValue(positive(range.min) && positive(range.max) && range.min <= range.max)
    budget = { min: range.min, max: range.max }
  }
  requireValue(row.allowed_modes.includes('budget') === !!budget)
  return {
    mode: 'selectable',
    allowed_modes: [...row.allowed_modes] as ConcreteReasoning['mode'][],
    effort_options: [...row.effort_options] as string[],
    budget,
  }
}
/** 解码独立选择对象，避免将接口缓存或未知字段直接作为表单草稿。 */
export function decodeSelection(value: unknown): ModelSelection {
  const row = object(value)
  requireValue(text(row.model_configuration_id))
  return {
    model_configuration_id: row.model_configuration_id,
    reasoning: decodeReasoning(row.reasoning),
  }
}
/** 校验会话选择字段；旧响应缺省兼容为空选择，显式损坏值仍拒绝。 */
export function decodeSelectionFields(value: unknown): SelectionFields {
  const row = object(value),
    version = row.model_selection_version === undefined ? 1 : row.model_selection_version,
    issue = row.model_selection_issue ?? null
  requireValue(
    positive(version) &&
      (issue === null ||
        [
          'model_deleted',
          'provider_disabled',
          'model_disabled',
          'model_unavailable',
          'reasoning_not_allowed',
        ].includes(String(issue))),
  )
  return {
    model_selection: row.model_selection == null ? null : decodeSelection(row.model_selection),
    model_selection_version: version,
    model_selection_issue: issue as SelectionIssue | null,
  }
}
/** 检查用户草稿是否仍在当前允许范围，固定值不匹配时要求明确重新选择。 */
export function validateSelection(
  selection: ModelSelection | null,
  model: SelectableModel | undefined,
): string {
  if (!selection) return '请选择模型方案'
  if (!model) return '原模型方案已停用或不可用，请重新选择'
  const control = model.reasoning_control,
    value = selection.reasoning
  if (control.mode === 'fixed')
    return JSON.stringify(decodeReasoning(value)) === JSON.stringify(control.default)
      ? ''
      : '原推理设置已改变，请重新选择'
  if (!control.allowed_modes.includes(value.mode)) return '推理方式超出当前允许范围，请重新选择'
  if (value.mode === 'effort' && !control.effort_options.includes(value.effort))
    return '推理档位超出当前允许范围，请重新选择'
  if (
    value.mode === 'budget' &&
    (!Number.isSafeInteger(value.budget_tokens) ||
      !control.budget ||
      value.budget_tokens < control.budget.min ||
      value.budget_tokens > control.budget.max)
  )
    return '思考预算须为允许区间内的整数'
  return ''
}
/** 解码已过滤的聊天选项，不允许重复连接或模型标识混淆选择。 */
export function decodeOptions(value: unknown): ModelOptions {
  const row = object(value)
  requireValue(Array.isArray(row.providers))
  const ids = new Set<string>(),
    connections = new Set<string>()
  const providers = row.providers.map((value) => {
    const provider = object(value)
    requireValue(
      text(provider.provider_configuration_id) &&
        text(provider.name) &&
        text(provider.provider) &&
        Array.isArray(provider.models),
    )
    requireValue(!connections.has(provider.provider_configuration_id))
    connections.add(provider.provider_configuration_id)
    const models = provider.models.map((value): SelectableModel => {
      const model = object(value),
        control = object(model.reasoning_control)
      requireValue(
        text(model.model_configuration_id) &&
          text(model.name) &&
          text(model.catalog_model_id) &&
          text(model.display_name) &&
          !ids.has(model.model_configuration_id),
      )
      ids.add(model.model_configuration_id)
      const result = {
        model_configuration_id: model.model_configuration_id,
        name: model.name,
        catalog_model_id: model.catalog_model_id,
        display_name: model.display_name,
        reasoning_control: { ...decodePolicy(control), default: decodeReasoning(control.default) },
      }
      requireValue(
        !validateSelection(
          {
            model_configuration_id: result.model_configuration_id,
            reasoning: result.reasoning_control.default,
          },
          result,
        ),
      )
      return result
    })
    return {
      provider_configuration_id: provider.provider_configuration_id,
      name: provider.name,
      provider: provider.provider,
      models,
    }
  })
  const selected = row.default_selection === null ? null : decodeSelection(row.default_selection)
  requireValue(
    !selected ||
      !validateSelection(
        selected,
        providers
          .flatMap((item) => item.models)
          .find((item) => item.model_configuration_id === selected.model_configuration_id),
      ),
  )
  return { providers, default_selection: selected }
}
/** 将服务端动态失效原因转成用户可理解的重选说明。 */
export const selectionIssueLabels: Record<SelectionIssue, string> = {
  model_deleted: '原模型方案已删除，请重新选择',
  provider_disabled: '原供应商连接已停用，请重新选择',
  model_disabled: '原模型方案已停用，请重新选择',
  model_unavailable: '原模型配置暂不可用，请重新选择',
  reasoning_not_allowed: '原推理设置超出当前限制，请重新选择',
}
