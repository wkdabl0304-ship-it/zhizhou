/** 浏览器验收启动策略：集中处理 Windows 回环短连接兼容性，生产浏览器不使用此配置。 */
import type { LaunchOptions } from '@playwright/test'

/** 为当前平台生成验收浏览器的启动选项，避免 Windows 随机端口分配造成间歇连接失败。
 * Windows 回退到系统默认端口分配，其他平台保持 Playwright 默认值；不重试请求或放宽断言。
 * 背景：https://groups.google.com/a/chromium.org/g/blink-dev/c/-Bmnni7Xv0A
 */
export function browserLaunchOptions(platform: NodeJS.Platform = process.platform): LaunchOptions {
  return platform === 'win32' ? { args: ['--disable-features=TcpPortRandomizationWin'] } : {}
}
