/** 首页标题预览回归：验证候选切换保留草稿，局部配色与试发不会修改已提交的正式应用状态。 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { TooltipProvider } from 'reka-ui'
import HeadingPreview from '@/views/HeadingPreview.vue'
import WelcomeHeading from '@/components/chat/WelcomeHeading.vue'
import { useChatStore } from '@/stores/chat'
import { THEME_STORAGE_KEY, useThemeStore } from '@/stores/theme'

let wrapper: VueWrapper | undefined

// 各测试使用独立 store，根主题与存储初始为空，防止比较页读取到上次测试的状态。
beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
})

// 卸载真实 Tooltip 与组件监听，并清除正式主题，保证后续聊天测试独立。
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  localStorage.clear()
  delete document.documentElement.dataset.theme
  document.documentElement.style.colorScheme = ''
  document.body.innerHTML = ''
})

/** 只替换导航链接，标签、输入区和提示均使用真实组件，覆盖组合边界。 */
function renderPreview(): VueWrapper {
  const Host = defineComponent({
    components: { TooltipProvider, HeadingPreview },
    template: '<TooltipProvider><HeadingPreview /></TooltipProvider>',
  })
  wrapper = mount(Host, {
    attachTo: document.body,
    global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
  return wrapper
}

describe('首页标题方案比较', () => {
  // 默认展示已采用宋体；比较历史方案时只替换标题，不重建草稿和真实输入组件。
  it('默认展示已采用标题，切换历史方案保留草稿，试发仅显示局部提示', async () => {
    const view = renderPreview()
    expect(view.get('.river-heading').text()).toBe('心有山海，自有知舟。')
    await view.get('textarea').setValue('尚未确定的标题想法')
    const input = view.get('textarea').element
    const tabs = view.findAll('[role="tab"]')
    expect(view.findComponent(WelcomeHeading).exists()).toBe(true)
    for (const tab of tabs.slice(0, 3)) {
      await tab.trigger('keydown', { key: 'Enter' })
      await flushPromises()
      expect(view.find('.study-heading').exists()).toBe(true)
      expect(view.get('textarea').element).toBe(input)
      expect((input as HTMLTextAreaElement).value).toBe('尚未确定的标题想法')
    }
    await tabs[3]!.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(view.find('.study-heading').exists()).toBe(false)
    expect(view.get('.river-heading').text()).toBe('心有山海，自有知舟。')
    await view.get('form').trigger('submit')
    await flushPromises()
    expect(view.get('[role="status"]').text()).toContain('尚未确定的标题想法')
    expect(document.activeElement).toBe(input)
    expect((input as HTMLTextAreaElement).value).toBe('')
  })

  // 局部主题必须覆盖根主题但不改写正式偏好，试发仍保留当前选定的宋体标题。
  it('局部主题与试发不改正式 store，当前预览保留已选宋体标题', async () => {
    const chat = useChatStore()
    chat.send('正式会话')
    const originalState = JSON.stringify(chat.$state)
    const theme = useThemeStore()
    theme.setTheme('dark')
    const view = renderPreview()
    expect(view.get('.theme-scope').attributes('data-theme')).toBe('light')
    await view.get('[aria-label="预览深色"]').trigger('click')
    expect(view.get('.theme-scope').attributes('data-theme')).toBe('dark')
    await view.get('[aria-label="预览浅色"]').trigger('click')
    await view.get('textarea').setValue('仅用于标题预览')
    await view.get('form').trigger('submit')
    await flushPromises()
    expect(JSON.stringify(chat.$state)).toBe(originalState)
    expect(theme.theme).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
    expect(localStorage.length).toBe(1)
    expect(view.findComponent(WelcomeHeading).exists()).toBe(true)
  })
})
