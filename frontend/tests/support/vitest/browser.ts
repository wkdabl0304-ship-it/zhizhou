/** 浏览器能力替身：只安装当前用例明确需要的媒体查询，不提供虚假的布局结果。 */
import { vi } from 'vitest'

/** 安装可主动切换的媒体查询，返回通知入口供测试验证响应式更新和监听清理。 */
export function installMediaQuery(matches = false) {
  const media = Object.assign(new EventTarget(), { matches, media: '(test)' })
  // 事件监听使用真实 EventTarget，浏览器 API 的恢复由公共 setup 负责。
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => media),
  )
  return {
    media,
    /** 修改匹配状态并发送标准 change 事件，不触发真实系统偏好。 */
    update(value: boolean): void {
      media.matches = value
      media.dispatchEvent(Object.assign(new Event('change'), { matches: value }))
    },
  }
}
