/** 上传上限的友好单位：界面使用 B/KB/MB/GB/TB，按 1024 换算并保持字节整数精度。 */
export const SIZE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB'] as const
export type SizeUnit = (typeof SIZE_UNITS)[number]
export const SIZE_UNIT_OPTIONS = SIZE_UNITS.map(
  // 使用熟悉的容量缩写作为界面值，说明文字另行交代 1024 换算约定。
  (unit) => ({ value: unit, label: unit === 'B' ? 'B（字节）' : unit }),
)
const MAX_BYTES = 1099511627776n

/** 把十进制容量换算成合法大小，不足一个字节拒绝，余数按最近字节保存。 */
export function parseUploadSize(value: string, unit: string): number | null {
  const index = SIZE_UNITS.indexOf(unit as SizeUnit)
  if (index < 0) return null
  const match = /^(\d+)(?:\.(\d+))?$/.exec(value.trim())
  if (!match || value.length > 80) return null
  const decimals = match[2] ?? ''
  const denominator = 10n ** BigInt(decimals.length)
  const multiplier = 1024n ** BigInt(index)
  const numerator = BigInt(match[1]! + decimals) * multiplier
  if (numerator < denominator || numerator > MAX_BYTES * denominator) return null
  return Number((numerator + denominator / 2n) / denominator)
}

/** 为已保存策略选择自然单位，最多四位小数供人阅读；表单另保留原值用于无改动保存。 */
export function editUploadSize(bytes: number): { value: string; unit: SizeUnit } {
  let index = 0
  while (index < SIZE_UNITS.length - 1 && bytes >= 1024 ** (index + 1)) index++
  const divisor = 1024n ** BigInt(index)
  const amount = BigInt(bytes)
  const rounded = (amount * 10000n + divisor / 2n) / divisor
  return { value: String(Number(rounded) / 10000), unit: SIZE_UNITS[index]! }
}
