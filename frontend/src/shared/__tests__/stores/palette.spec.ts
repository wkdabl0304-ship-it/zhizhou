/** 主题可读性回归：读取实际颜色变量，验证明暗方案正文、辅助文字和操作色的对比度。 */
import { expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
// Vitest 不注入样式；直接读取实际变量文件，避免把 CSS 模块替身误当成真实色板。
const source = readFileSync(resolve(process.cwd(), 'src/styles/tokens.css'), 'utf8')

/** 将 sRGB 颜色转换为相对亮度，用于计算 WCAG 对比度。 */
function luminance(color: string): number {
  const channels = [1, 3, 5].map((offset) => {
    const value = parseInt(color.slice(offset, offset + 2), 16) / 255
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  })
  return channels[0]! * 0.2126 + channels[1]! * 0.7152 + channels[2]! * 0.0722
}

it.each(['light', 'dark'])(
  '%s 的关键文字与界面色达到正常字号对比度，主辅色各有独立色板',
  (theme) => {
    const blocks = source.split(":root[data-theme='dark']")
    const colors = Object.fromEntries(
      [...blocks[theme === 'light' ? 0 : 1]!.matchAll(/(--[\w-]+):\s*(#[\da-f]{6});/g)].map(
        (match) => [match[1], match[2]],
      ),
    )
    const pairs = [
      ['text', 'bg'],
      ['text', 'surface'],
      ['text-secondary', 'surface'],
      ['text-muted', 'surface'],
      ['text-muted', 'surface-soft'],
      ['brand', 'brand-soft'],
      ['accent', 'accent-soft'],
      ['accent', 'bg'],
      ['action-contrast', 'action'],
      ['brand-contrast', 'brand'],
      ['text', 'sidebar-bg'],
      ['text-secondary', 'surface-active'],
    ]
    for (const [foreground, background] of pairs) {
      const a = luminance(colors['--' + foreground]!),
        b = luminance(colors['--' + background]!)
      expect((Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)).toBeGreaterThanOrEqual(4.5)
    }
    expect(colors['--brand']).not.toBe(colors['--accent'])
  },
)
