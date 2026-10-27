/** 会话标题规则：与后端保持 Unicode 空白规范化及字符计数一致，供临时标题和编辑共用。 */
export const TITLE_LIMIT = 100

/** 合并 Python str.split 识别的空白，保留并非空白的 BOM 字符。 */
export function normalizeTitle(value: string): string {
  // Python 除 Unicode White_Space 外还识别四个信息分隔符，先将它们转为普通空格。
  return value
    .replaceAll('\u001c', ' ')
    .replaceAll('\u001d', ' ')
    .replaceAll('\u001e', ' ')
    .replaceAll('\u001f', ' ')
    .replace(/\p{White_Space}+/gu, ' ')
    .replace(/^ | $/g, '')
}

/** 验证规范化后的标题是否为 1–100 个 Unicode 字符，不按 UTF-16 长度误判表情。 */
export function titleIssue(value: string): string {
  const length = Array.from(normalizeTitle(value)).length
  return !length ? '请输入会话标题' : length > TITLE_LIMIT ? '标题最多 100 个字符' : ''
}
