/** 会话页面集成：真实侧栏、历史 Markdown、游标按钮和删除确认，不连接模型与数据库。 */
import { createTestPinia as createPinia } from '@tests/support/vitest/mount'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DOMWrapper, mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { disposePinia, type Pinia } from 'pinia'
import { defineComponent } from 'vue'
import { TooltipProvider } from 'reka-ui'
import { RouterView, createMemoryHistory } from 'vue-router'
import { createAppRouter } from '@/router'
import { useModelConfigStore } from '@/features/model-config/store'
import { modelConfigData } from '@tests/support/data/model-config'
import { useChatStore } from '@/features/chat/store'
import { authenticate } from '@tests/support/vitest/auth'
import { A, B, info, turn } from '@tests/support/data/chat'
import { response } from '@tests/support/vitest/http'
import { withModelOptions } from '@tests/support/vitest/chat'

let pinia: Pinia
let wrapper: VueWrapper | undefined
const fetchMock = vi.fn<typeof fetch>()
// 使用真实认证状态和媒体监听接口，只替换 HTTP 与浏览器断点。
beforeEach(async () => {
  pinia = createPinia()
  fetchMock.mockReset()
  vi.stubGlobal('fetch', withModelOptions(fetchMock))
  vi.stubGlobal('matchMedia', () => ({
    matches: false,
    addEventListener: vi.fn<() => void>(),
    removeEventListener: vi.fn<() => void>(),
  }))
  await authenticate(pinia, fetchMock, true)
  // 历史与目录可以独立于模型配置验证，完整默认加载另由应用集成覆盖。
  useModelConfigStore(pinia).selected = modelConfigData().selected
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
  const router = createAppRouter(createMemoryHistory())
  await router.push('/')
  await router.isReady()
  const Host = defineComponent({
    components: { TooltipProvider, RouterView },
    template: '<TooltipProvider><RouterView /></TooltipProvider>',
  })
  wrapper = mount(Host, {
    attachTo: document.body,
    global: { plugins: [pinia, router] },
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
    await flushPromises()
    const confirmation = new DOMWrapper(document.querySelector('[role="dialog"]')!)
    await confirmation.get('[data-confirm-cancel]').trigger('click')
    await flushPromises()
    expect(fetchMock.mock.calls.filter(([, options]) => options?.method === 'DELETE')).toHaveLength(
      0,
    )
    await page.get('[aria-label="删除会话：历史话题"]').trigger('click')
    await flushPromises()
    await new DOMWrapper(document.querySelector('[role="dialog"]')!)
      .findAll('button')
      .at(-1)!
      .trigger('click')
    await flushPromises()
    expect(page.findAll('.conversation-item')).toHaveLength(1)
    expect(page.find('.welcome').exists()).toBe(true)
    expect((page.get('textarea').element as HTMLTextAreaElement).value).toBe('')
  })

  // 服务不可用时保留用户可见重试入口，不把请求失败描述为没有会话。
  it('目录无刷新按钮，失败时通过重试恢复目录', async () => {
    fetchMock
      .mockRejectedValueOnce(new TypeError('offline'))
      .mockResolvedValueOnce(response({ items: [info()], next_cursor: null }))
    const page = await open()
    expect(page.get('[role="alert"]').text()).toContain('网络连接失败')
    await page.get('.ui-feedback-actions button').trigger('click')
    await flushPromises()
    expect(page.find('[role="alert"]').exists()).toBe(false)
    expect(page.get('.conversation-item').text()).toContain('历史话题')
  })
})

// 编辑由侧栏发起、状态层 PATCH 后同步到页头；消息草稿不参与标题保存。
it('侧栏弹窗改名更新列表与页头，取消和保存都恢复焦点且不清空消息草稿', async () => {
  let title = '历史话题'
  fetchMock.mockImplementation(async (url, init) => {
    if (init?.method === 'PATCH' && String(url).endsWith('/title')) {
      title = JSON.parse(String(init.body)).title
      return response(info(A, title))
    }
    if (String(url).includes('/' + A + '?'))
      return response({ conversation: info(A, title), items: [turn()], next_cursor: null })
    return response({ items: [info(A, title)], next_cursor: null })
  })
  const page = await open()
  await page.get('.conversation-item').trigger('click')
  await flushPromises()
  await page.get('textarea').setValue('消息草稿')
  await page.get('[aria-label="修改会话标题：历史话题"]').trigger('click')
  await flushPromises()
  await new DOMWrapper(document.querySelector('[name="conversation_title"]')!).setValue('取消输入')
  await new DOMWrapper(document.querySelector('[name="conversation_title"]')!).trigger('keydown', {
    key: 'Escape',
  })
  await flushPromises()
  expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'PATCH')).toHaveLength(0)
  await vi.waitFor(() =>
    expect(document.activeElement).toBe(page.get('[aria-label="修改会话标题：历史话题"]').element),
  )
  await page.get('[aria-label="修改会话标题：历史话题"]').trigger('click')
  await flushPromises()
  await new DOMWrapper(document.querySelector('[name="conversation_title"]')!).setValue(
    '  学习  Vue  ',
  )
  await new DOMWrapper(document.querySelector('form[aria-label="修改会话标题"]')!).trigger('submit')
  await flushPromises()
  expect(page.get('.header-title').text()).toBe('学习 Vue')
  expect(page.get('.conversation-item').text()).toContain('学习 Vue')
  expect((page.get('textarea').element as HTMLTextAreaElement).value).toBe('消息草稿')
  expect(document.querySelector('[name="conversation_title"]')).toBeNull()
  await vi.waitFor(() =>
    expect(document.activeElement).toBe(page.get('[aria-label="修改会话标题：学习 Vue"]').element),
  )
})

// 自动同步仅轮询当前远端生成会话；完成后停止，不能要求用户点击刷新。
it('远端生成完成后自动同步历史，完成和卸载后释放轮询定时器', async () => {
  let complete = false
  fetchMock.mockImplementation(async (url) =>
    String(url).includes('/' + A + '?')
      ? response({
          conversation: info(),
          items: [turn(1, complete ? 'completed' : 'running')],
          next_cursor: null,
        })
      : response({ items: [info()], next_cursor: null }),
  )
  const page = await open()
  vi.useFakeTimers()
  try {
    await page.get('.conversation-item').trigger('click')
    await flushPromises()
    expect(useChatStore().activeConversation?.remoteRunning).toBe(true)
    expect(page.text()).toContain('完成后将自动同步')
    expect(page.findAll('button').some((button) => button.text().includes('刷新'))).toBe(false)
    complete = true
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(useChatStore().activeConversation?.remoteRunning).toBe(false)
    expect(page.get('.markdown-content strong').text()).toBe('回答1')
    const reads = fetchMock.mock.calls.length
    await vi.advanceTimersByTimeAsync(6000)
    expect(fetchMock.mock.calls).toHaveLength(reads)
    wrapper?.unmount()
    wrapper = undefined
    await vi.advanceTimersByTimeAsync(6000)
    expect(fetchMock.mock.calls).toHaveLength(reads)
  } finally {
    vi.useRealTimers()
  }
})

// 让远端轮次始终保持 running，验证清理确实由页面生命周期触发，而不是被完成状态提前停止。
it('隐藏窗口暂停轮询请求，离开聊天及卸载工作区时停止仍活跃的轮询', async () => {
  const data = modelConfigData()
  fetchMock.mockImplementation(async (input) => {
    const url = String(input)
    if (url.includes('/' + A + '?'))
      return response({ conversation: info(), items: [turn(1, 'running')], next_cursor: null })
    if (url.endsWith('/catalog/providers')) return response([data.brand])
    if (url.endsWith('/provider-configurations')) return response([data.provider])
    if (url.endsWith('/models')) return response([data.model])
    if (url.endsWith('/default')) return response(data.selected)
    return response({ items: [info()], next_cursor: null })
  })
  const page = await open()
  // 只统计真实历史接口，忽略路由挂载时正常的模型选项及管理快照请求。
  const reads = () =>
    fetchMock.mock.calls.filter(([url]) => String(url).includes('/' + A + '?')).length
  const hidden = vi.spyOn(document, 'hidden', 'get')
  vi.useFakeTimers()
  try {
    await page.get('.conversation-item').trigger('click')
    await flushPromises()
    expect(useChatStore().activeConversation?.remoteRunning).toBe(true)
    hidden.mockReturnValue(true)
    const beforeHidden = reads()
    await vi.advanceTimersByTimeAsync(4000)
    expect(reads()).toBe(beforeHidden)
    hidden.mockReturnValue(false)
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(reads()).toBe(beforeHidden + 1)

    await page.vm.$router.push('/models')
    await flushPromises()
    const beforeLeave = reads()
    await vi.advanceTimersByTimeAsync(4000)
    expect(reads()).toBe(beforeLeave)
    await page.vm.$router.push('/')
    await flushPromises()
    const beforeReturn = reads()
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(reads()).toBe(beforeReturn + 1)
    expect(useChatStore().activeConversation?.remoteRunning).toBe(true)

    wrapper?.unmount()
    wrapper = undefined
    const beforeUnmount = reads()
    await vi.advanceTimersByTimeAsync(4000)
    expect(reads()).toBe(beforeUnmount)
  } finally {
    hidden.mockRestore()
    vi.useRealTimers()
  }
})
