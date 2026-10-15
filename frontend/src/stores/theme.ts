/** 主题状态：只保存外观偏好，在根元素应用主题，使 Teleport 弹层共享相同变量。 */
import { ref } from 'vue'
import { defineStore } from 'pinia'

export type Theme = 'light' | 'dark'
export const THEME_STORAGE_KEY = 'zhizhou-theme'

export const useThemeStore = defineStore('theme', () => {
  const theme = ref<Theme>('light')

  /** 应用合法主题；存储不可用时仍允许切换，聊天内容不会写入存储。 */
  function setTheme(value: Theme): void {
    theme.value = value
    document.documentElement.dataset.theme = value
    document.documentElement.style.colorScheme = value
    try {
      localStorage.setItem(THEME_STORAGE_KEY, value)
    } catch {
      // 隐私模式或存储配额不影响当前页面的外观切换。
    }
  }

  /** 在应用挂载时恢复偏好；缺失、非法值或读取失败均回退到浅色。 */
  function initialize(): void {
    let saved: string | null = null
    try {
      saved = localStorage.getItem(THEME_STORAGE_KEY)
    } catch {
      // 存储不可读时使用产品默认浅色主题。
    }
    setTheme(saved === 'dark' ? 'dark' : 'light')
  }

  return { theme, setTheme, initialize }
})
