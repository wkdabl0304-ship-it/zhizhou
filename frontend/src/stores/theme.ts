/** 主题状态：只保存外观偏好，在根元素应用主题，使 Teleport 弹层共享相同变量。 */
import { ref } from 'vue'
import { defineStore } from 'pinia'

export type Theme = 'light' | 'dark'
export const THEME_STORAGE_KEY = 'zhizhou-theme'

/** 创建全局主题状态，供页面和 Teleport 弹层共享同一外观偏好。 */
export const useThemeStore = defineStore('theme', () => {
  const theme = ref<Theme>('light')

  /**
   * 切换页面主题并保存外观偏好。
   * value 由调用方限定为合法主题，更新根元素和浏览器色彩方案后写入 localStorage；
   * 存储不可用时仍完成当前页面切换，不保存聊天内容。
   */
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

  /** 从浏览器存储恢复主题并应用到页面；缺失、非法值或读取失败均回退到浅色。 */
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
