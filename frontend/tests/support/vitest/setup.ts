/** Vitest 公共收尾：先卸载组件与状态，再恢复浏览器替身，避免副作用跨用例传播。 */
import { enableAutoUnmount } from '@vue/test-utils'
import { afterEach, vi } from 'vitest'
import { disposeTestPinia } from './mount'
let unmountComponents: () => void = () => {}
// 将组件收尾纳入同一个钩子，避免运行器逆序调用钩子时先清空 DOM。
enableAutoUnmount((cleanup) => {
  unmountComponents = cleanup
})

// 此处只恢复环境；媒体、布局和剪贴板替身必须由需要它们的测试显式安装。
afterEach(() => {
  unmountComponents()
  disposeTestPinia()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  vi.useRealTimers()
  sessionStorage.clear()
  localStorage.clear()
  document.body.replaceChildren()
  delete document.documentElement.dataset.theme
  document.documentElement.style.colorScheme = ''
})
