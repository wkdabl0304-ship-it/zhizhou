/** 主题回归：隔离 localStorage 与 DOM 根节点，检查合法恢复及存储异常下的降级行为。 */
import { createTestPinia as createPinia } from '@tests/support/vitest/mount'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { setActivePinia } from 'pinia'
import { THEME_STORAGE_KEY, useThemeStore } from '@/shared/stores/theme'

// 每项测试从浅色、空存储开始，不依赖运行顺序或开发者浏览器偏好。
beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  delete document.documentElement.dataset.theme
})
// 恢复存储替身和主题 DOM，避免干扰其他组件测试。
afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
  delete document.documentElement.dataset.theme
  document.documentElement.style.colorScheme = ''
})

describe('主题偏好', () => {
  // 未设置与非法值都采用产品默认主题。
  it('默认浅色，并拒绝非法存储值', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'invalid')
    const theme = useThemeStore()
    theme.initialize()
    expect(theme.theme).toBe('light')
    expect(document.documentElement.dataset.theme).toBe('light')
  })

  // 根节点持有变量，使独立 Portal 可以继承相同外观。
  it('恢复深色并在切换时保存偏好', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'dark')
    const theme = useThemeStore()
    theme.initialize()
    expect(document.documentElement.dataset.theme).toBe('dark')
    theme.setTheme('light')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
    expect(document.documentElement.style.colorScheme).toBe('light')
  })

  // 模拟隐私模式拒绝读写；页面仍需正常初始化并允许临时切换。
  it('存储拒绝访问时仍能切换', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('denied')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('denied')
    })
    const theme = useThemeStore()
    expect(() => theme.initialize()).not.toThrow()
    theme.setTheme('dark')
    expect(theme.theme).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
  })
})
