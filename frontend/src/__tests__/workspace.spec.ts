/** 工作空间集成回归：验证示例填入、发送后的焦点和会话切换；不连接网络或数据库。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent } from 'vue'
import { TooltipProvider } from 'reka-ui'
import ChatView from '@/views/ChatView.vue'
import WelcomeHeading from '@/components/chat/WelcomeHeading.vue'

const wrappers: VueWrapper[] = []
// jsdom 没有真实视口断点；桌面替身只提供组件实际使用的媒体查询监听接口。
beforeEach(() => {
  vi.stubGlobal('matchMedia', () => ({
    matches: false,
    addEventListener: vi.fn<() => void>(),
    removeEventListener: vi.fn<() => void>(),
  }))
})
// 卸载组件后再恢复全局替身，确保监听清理调用仍能访问原替身。
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

/** 用真实 Pinia 与 TooltipProvider 组合页面，只替换无关的路由链接。 */
function renderWorkspace() {
  const Host = defineComponent({
    components: { TooltipProvider, ChatView },
    template: '<TooltipProvider><ChatView /></TooltipProvider>',
  })
  const wrapper = mount(Host, {
    attachTo: document.body,
    global: { plugins: [createPinia()], stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
  wrappers.push(wrapper)
  return wrapper
}

describe('聊天工作空间', () => {
  // 首页输入实例会在发送时被替换，必须将焦点送到新对话页的输入框。
  it('建议只填入草稿，发送后创建对话并保持输入焦点', async () => {
    const wrapper = renderWorkspace()
    // 正式首页必须使用已选现代宋体组件，防止只更新开发预览而遗漏实际入口。
    expect(wrapper.findComponent(WelcomeHeading).exists()).toBe(true)
    await wrapper.get('.suggestion').trigger('click')
    expect(wrapper.findAll('article')).toHaveLength(0)
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toContain('入职清单')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.findAll('article')).toHaveLength(2)
    expect(document.activeElement).toBe(wrapper.get('textarea').element)
    expect(wrapper.text()).toContain('固定演示回复')
  })

  // 草稿不跨会话携带，防止切换后误发；会话正文仍由各自数据恢复。
  it('切换会话与新建时清除草稿', async () => {
    const wrapper = renderWorkspace()
    await wrapper.get('textarea').setValue('未发送的内容')
    await wrapper.get('.conversation-item').trigger('click')
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('')
    expect(wrapper.findAll('article')).toHaveLength(2)
    await wrapper.get('.new-chat-button').trigger('click')
    expect(wrapper.findAll('article')).toHaveLength(0)
    expect(wrapper.find('.welcome').exists()).toBe(true)
  })
})
