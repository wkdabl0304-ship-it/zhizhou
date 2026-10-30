/** 公开模型身份解码：流与历史共用字段白名单，不把执行参数或凭据传入界面。 */
import { ApiError } from '@/features/auth/authenticated'
import type { ModelIdentity } from './types'

/** 校验可选模型身份；旧响应缺失时返回 null，损坏的新字段明确拒绝。 */
export function decodeModelIdentity(value: unknown): ModelIdentity | null {
  if (value === undefined || value === null) return null
  if (typeof value !== 'object' || Array.isArray(value)) throw new ApiError('模型身份格式无效')
  const row = value as Record<string, unknown>
  const keys = ['model_configuration_id', 'catalog_model_id', 'display_name'] as const
  if (keys.some((key) => typeof row[key] !== 'string' || !row[key].trim()))
    throw new ApiError('模型身份格式无效')
  return {
    model_configuration_id: row.model_configuration_id as string,
    catalog_model_id: row.catalog_model_id as string,
    display_name: row.display_name as string,
  }
}
