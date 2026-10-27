/** 山海背景回归：明暗方案更换独立素材，图片加载前显示主题画布，减少动态效果入口保持有效。 */
import { expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createTestPinia } from '@tests/support/vitest/mount'
import { useThemeStore } from '@/shared/stores/theme'
import RiverBackdrop from '../../components/RiverBackdrop.vue'

it('切换深色实际更换夜景素材，载入前隐藏旧画面，回到浅色恢复原图', async () => {
  const pinia = createTestPinia(),
    theme = useThemeStore(pinia)
  const page = mount(RiverBackdrop, { props: { motion: false }, global: { plugins: [pinia] } })
  const image = page.get('img')
  const day = image.attributes('src')
  expect(day).toContain('indigo-ink')
  await image.trigger('load')
  expect(image.classes()).toContain('is-loaded')
  theme.setTheme('dark')
  await nextTick()
  expect(image.attributes('src')).toContain('indigo-night')
  expect(image.attributes('src')).not.toBe(day)
  expect(image.classes()).not.toContain('is-loaded')
  await image.trigger('load')
  expect(image.classes()).toContain('is-loaded')
  expect(page.attributes('data-theme')).toBe('dark')
  expect(page.attributes('data-motion')).toBe('off')
  theme.setTheme('light')
  await nextTick()
  expect(image.attributes('src')).toBe(day)
})
