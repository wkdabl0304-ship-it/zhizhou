/** 浏览器启动兼容性：验证仅 Windows 调整端口分配，其他平台和后续调用保持独立默认值。 */
import { expect, it } from 'vitest'
import { browserLaunchOptions } from '../playwright/browser'

it('Windows 验收浏览器只回退端口分配，不关闭安全隔离或修改请求重试', () => {
  expect(browserLaunchOptions('win32')).toEqual({
    args: ['--disable-features=TcpPortRandomizationWin'],
  })
})

it.each(['linux', 'darwin'] as const)('%s 保留默认启动选项', (platform) => {
  expect(browserLaunchOptions(platform)).toEqual({})
})

it('每次启动取得独立选项，调用方的附加参数不会污染下一次浏览器', () => {
  const options = browserLaunchOptions('win32')
  options.args!.push('--test-only')
  expect(browserLaunchOptions('win32').args).toEqual(['--disable-features=TcpPortRandomizationWin'])
})
