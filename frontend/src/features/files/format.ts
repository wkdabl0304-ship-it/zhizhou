/** 资料库显示与输入规则：二进制容量单位、名称规范和错误提示。 */
import { ApiError } from '@/features/auth/authenticated'

export const SPACE_LABELS = { global: '全局共享', department: '部门协作', personal: '个人收藏' }

/** 按二进制单位显示容量，保留零字节和目录的差别。 */
export function formatSize(bytes: number | null): string {
  if (bytes === null) return '—'
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), 4)
  return `${Number((bytes / 1024 ** exponent).toFixed(2))} ${units[exponent - 1]}`
}

/** 将公开时间转为本地可读时间，完整日期仍通过 title 提供。 */
export function formatDate(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

/** 在提交前检查与后端一致的基础名称约束，最终判重仍由服务端完成。 */
export function validateName(value: string): string {
  const name = value.trim().normalize('NFC')
  if (!name || [...name].length > 255) return '名称须为 1～255 个字符。'
  if (name === '.' || name === '..' || /[/\\\p{Cc}]/u.test(name))
    return '名称不能是 . 或 ..，也不能包含路径分隔符或控制字符。'
  return ''
}

/** 为版本冲突和网络中断补充可执行说明，不自动重新提交写入。 */
export function fileError(failure: unknown): string {
  if (!(failure instanceof ApiError)) return '操作未完成，请稍后重试。'
  if ([40910, 40911].includes(failure.code ?? 0))
    return '内容已被其他操作更新。请关闭此窗口，重新查看后再操作。'
  return failure.message
}
