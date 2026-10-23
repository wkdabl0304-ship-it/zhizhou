/** 会话页面集成：真实侧栏、历史 Markdown、游标按钮和删除确认，不连接模型与数据库。 */
import { createTestPinia as createPinia } from '@tests/support/vitest/mount'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { disposePinia, type Pinia } from 'pinia'
import { defineComponent } from 'vue'
import { TooltipProvider } from 'reka-ui'
import ChatView from '@/views/ChatView.vue'
import { authenticate } from '@tests/support/vitest/auth'
import { A, B, info, turn } from '@tests/support/data/chat'
import { response } from '@tests/support/vitest/http'

let pinia: Pinia
let wrapper: VueWrapper | undefined
const fetchMock = vi.fn<typeof fetch>()
// 使用真实认证状态和媒体监听接口，只替换 HTTP 与浏览器断点。
beforeEach(async () => {
  pinia = createPinia()
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('matchMedia', () => ({
    matches: false,
    addEventListener: vi.fn<() => void>(),
    removeEventListener: vi.fn<() => void>(),
  }))
  await authenticate(pinia, fetchMock)
})
// 页面卸载后才销毁状态和全局替身，确保请求与监听按真实生命周期清理。
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  disposePinia(pinia)
  vi.unstubAllGlobals()
  sessionStorage.clear()
})

/** 挂载具有真实 Tooltip 上下文的工作区，保留首次会话目录请求。 */
async function open() {
  const Host = defineComponent({
    components: { TooltipProvider, ChatView },
    template: '<TooltipProvider><ChatView /></TooltipProvider>',
  })
  wrapper = mount(Host, {
    global: { plugins: [pinia], stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
  await flushPromises()
  return wrapper
}

describe('会话导航与历史界面', () => {
  // 从首次目录加载开始验证整条用户流程，删除必须明确确认且成功后才移除。
  it('展示账号目录、加载历史与更早记录，取消删除不请求接口', async () => {
    fetchMock.mockImplementation(async (url, options) => {
      if (options?.method === 'DELETE') return response(null)
      if (String(url).includes(`/${A}?`))
        return response({
          conversation: info(),
          items: String(url).includes('cursor=') ? [turn(1)] : [turn(2)],
          next_cursor: String(url).includes('cursor=') ? null : 'old-turns',
        })
      if (String(url).includes('cursor='))
        return response({ items: [info(B, '较早会话')], next_cursor: null })
      return response({ items: [info()], next_cursor: 'old-conversations' })
    })
    const page = await open()
    expect(page.get('.conversation-item').text()).toContain('历史话题')
    expect(page.text()).not.toContain('仅本次浏览')
    await page.get('.conversation-item').trigger('click')
    await flushPromises()
    expect(page.get('.markdown-content strong').text()).toBe('回答2')
    const earlier = page.findAll('button').find((button) => button.text() === '加载更早消息')!
    await earlier.trigger('click')
    await flushPromises()
    expect(page.findAll('.markdown-content strong').map((node) => node.text())).toEqual([
      '回答1',
      '回答2',
    ])
    const more = page.findAll('button').find((button) => button.text() === '加载更早会话')!
    await more.trigger('click')
    await flushPromises()
    expect(page.findAll('.conversation-item')).toHaveLength(2)
    await page.get('textarea').setValue('当前会话未发送的草稿')
    await page.get('[aria-label="删除会话：历史话题"]').trigger('click')
    const confirmation = page.get('[aria-label="确认删除会话：历史话题"]')
    await confirmation.findAll('button')[1]!.trigger('click')
    expect(fetchMock.mock.calls.filter(([, options]) => options?.method === 'DELETE')).toHaveLength(
      0,
    )
    await page.get('[aria-label="删除会话：历史话题"]').trigger('click')
    await page.get('[aria-label="确认删除会话：历史话题"]').findAll('button')[0]!.trigger('click')
    await flushPromises()
    expect(page.findAll('.conversation-item')).toHaveLength(1)
    expect(page.find('.welcome').exists()).toBe(true)
    expect((page.get('textarea').element as HTMLTextAreaElement).value).toBe('')
  })

  // 服务不可用时保留用户可见重试入口，不把请求失败描述为没有会话。
  it('目录失败显示原因，刷新后恢复目录', async () => {
    fetchMock
      .mockRejectedValueOnce(new TypeError('offline'))
      .mockResolvedValueOnce(response({ items: [info()], next_cursor: null }))
    const page = await open()
    expect(page.get('[role="alert"]').text()).toContain('网络连接失败')
    await page.get('.directory-action').trigger('click')
    await flushPromises()
    expect(page.find('[role="alert"]').exists()).toBe(false)
    expect(page.get('.conversation-item').text()).toContain('历史话题')
  })
})
