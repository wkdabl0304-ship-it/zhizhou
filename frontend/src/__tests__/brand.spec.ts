/** 品牌探索回归：检查局部主题和会话隔离、方案切换、输入焦点以及动效生命周期。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { TooltipProvider } from 'reka-ui'
import BrandPreview from '@/views/BrandPreview.vue'
import { useChatStore } from '@/stores/chat'
import { useThemeStore, THEME_STORAGE_KEY } from '@/stores/theme'
import { useBrandPrototype } from '@/components/brand/useBrandPrototype'
import { useMotionPreference } from '@/composables/useMotionPreference'

const wrappers: VueWrapper[] = []
const mediaQueries = new Map<string, EventTarget & { matches: boolean }>()

/** 提供可触发 change 的媒体查询替身，不修改测试进程或真实浏览器的系统偏好。 */
function matchMedia(query: string): MediaQueryList {
  let media = mediaQueries.get(query)
  if (!media) {
    media = Object.assign(new EventTarget(), { matches: false, media: query })
    mediaQueries.set(query, media)
  }
  return media as unknown as MediaQueryList
}

// 每项测试创建独立的正式 store 和媒体查询，防止状态被上一个品牌场景污染。
beforeEach(() => {
  setActivePinia(createPinia())
  vi.stubGlobal('matchMedia', matchMedia)
  localStorage.clear()
})

// 先卸载组件以触发监听清理，再恢复文档可见性替身、主题和存储。
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  mediaQueries.clear()
  localStorage.clear()
  delete document.documentElement.dataset.theme
  document.documentElement.style.colorScheme = ''
  document.body.innerHTML = ''
})

/** 以真实 Reka 标签、Tooltip 与原生输入挂载完整预览，只替换无关的路由链接。 */
function renderPreview() {
  const Host = defineComponent({
    components: { TooltipProvider, BrandPreview },
    template: '<TooltipProvider><BrandPreview /></TooltipProvider>',
  })
  const wrapper = mount(Host, {
    attachTo: document.body,
    global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
  wrappers.push(wrapper)
  return wrapper
}

describe('品牌视觉原型', () => {
  // 三种外观应能比较同一份已发送内容，避免切换标签造成原型重建和会话丢失。
  it('默认展示朱砂浅色首页，切换方案保留演示会话并恢复发送焦点', async () => {
    const wrapper = renderPreview()
    expect(wrapper.get('.brand-surface').classes()).toContain('brand-paper')
    expect(wrapper.get('.brand-surface').attributes('data-theme')).toBe('light')
    expect(wrapper.get('.brand-surface').attributes('data-motion')).toBe('on')
    await wrapper.get('textarea').setValue('我的品牌测试内容')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('.b-messages').text()).toContain('我的品牌测试内容')
    expect(document.activeElement).toBe(wrapper.get('textarea').element)
    // 使用原生键盘激活标签，验证 Reka 组合后的方案切换而非调用组件内部方法。
    await wrapper.findAll('[role="tab"]')[1]!.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(wrapper.get('.brand-surface').classes()).toContain('brand-river')
    expect(wrapper.get('.b-messages').text()).toContain('我的品牌测试内容')
    expect(wrapper.findAll('.b-message')).toHaveLength(2)
  })

  // 品牌页主题与正式 store、根节点、localStorage 都隔离；样例消息也不得写回正式会话。
  it('局部主题和演示操作不会修改正式应用状态', async () => {
    const chat = useChatStore()
    chat.send('正式页面的草稿会话')
    const initialChat = JSON.stringify(chat.$state)
    const theme = useThemeStore()
    theme.setTheme('dark')
    const wrapper = renderPreview()
    expect(wrapper.get('.brand-surface').attributes('data-theme')).toBe('light')
    await wrapper.get('[aria-label="原型深色"]').trigger('click')
    await wrapper.get('[aria-label="原型浅色"]').trigger('click')
    await wrapper.get('textarea').setValue('品牌预览的内容')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(JSON.stringify(chat.$state)).toBe(initialChat)
    expect(theme.theme).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
    expect(localStorage.length).toBe(1)
  })

  // 点击首页示例只能填入，不自动产生消息；不同原型实例也不能共享修改后的演示数据。
  it('示例只填草稿，空白不发送，新实例恢复独立样例', async () => {
    const wrapper = renderPreview()
    await wrapper.get('.b-suggestions button').trigger('click')
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('梳理一个新想法')
    expect(wrapper.findAll('.b-message')).toHaveLength(0)
    const first = useBrandPrototype()
    const second = useBrandPrototype()
    expect(first.send(' \n ')).toBe(false)
    first.selectConversation('weekly')
    first.send('追加原型消息')
    expect(first.activeConversation.value?.messages).toHaveLength(4)
    expect(second.conversations.value.find((item) => item.id === 'weekly')?.messages).toHaveLength(
      2,
    )
  })

  // 动效开关独立于系统设置；减少动态效果优先，不把请求开启误当作实际播放。
  it('支持关闭动效，并响应系统减少动态效果', async () => {
    const wrapper = renderPreview()
    const reduced = mediaQueries.get('(prefers-reduced-motion: reduce)')!
    reduced.matches = true
    reduced.dispatchEvent(Object.assign(new Event('change'), { matches: true }))
    await nextTick()
    expect(wrapper.get('.brand-surface').attributes('data-motion')).toBe('off')
    expect(wrapper.get('.lab-motion').text()).toContain('系统减少动效')
    reduced.matches = false
    reduced.dispatchEvent(Object.assign(new Event('change'), { matches: false }))
    await nextTick()
    expect(wrapper.get('.brand-surface').attributes('data-motion')).toBe('on')
    await wrapper.get('.lab-motion').trigger('click')
    expect(wrapper.get('.brand-surface').attributes('data-motion')).toBe('off')
  })

  // 后台暂停不会改变用户的开关；离开页面后可见性监听必须解除，避免影响正式界面。
  it('页面隐藏时暂停，卸载后不再响应可见性事件', async () => {
    let motion: ReturnType<typeof useMotionPreference> | undefined
    const Host = defineComponent({
      // 保留组合函数返回值，验证组件卸载后外部事件不再更新它。
      setup() {
        motion = useMotionPreference()
        return {}
      },
      template: '<div />',
    })
    const wrapper = mount(Host)
    const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
    document.dispatchEvent(new Event('visibilitychange'))
    await nextTick()
    expect(motion!.visible.value).toBe(false)
    expect(motion!.requested.value).toBe(true)
    expect(motion!.enabled.value).toBe(true)
    wrapper.unmount()
    visibility.mockReturnValue('visible')
    document.dispatchEvent(new Event('visibilitychange'))
    expect(motion!.visible.value).toBe(false)
  })
})
