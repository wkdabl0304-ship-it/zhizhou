/** 标题跨层集成：真实工作区、SSE、接口解码和状态合并贯通，网络以契约替身隔离。 */
import { beforeEach, expect, it, vi } from 'vitest'
import { DOMWrapper, mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'
import App from '@/App.vue'
import { createAppRouter } from '@/router'
import { useChatStore } from '@/features/chat/store'
import { createTestPinia } from '@tests/support/vitest/mount'
import { authenticate } from '@tests/support/vitest/auth'
import { installMediaQuery } from '@tests/support/vitest/browser'
import { A, info } from '@tests/support/data/chat'
import { modelOptionsData } from '@tests/support/data/model-selection'
import { response } from '@tests/support/vitest/http'
import { controlledStream } from '@tests/support/vitest/sse'
import { eventFrame } from '@tests/support/vitest/chat'

const fetchMock = vi.fn<typeof fetch>()
beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  installMediaQuery()
})

it('完成后自动标题同时更新页头和目录，手动保存保留消息草稿与模型选择', async () => {
  const pinia = createTestPinia(),
    stream = controlledStream()
  await authenticate(pinia, fetchMock)
  let title = '原始问题',
    created = false
  fetchMock.mockImplementation(async (input, init) => {
    const url = String(input)
    if (url.endsWith('/options')) return response(modelOptionsData())
    if (url === '/api/chat') {
      created = true
      return stream.response
    }
    if (init?.method === 'PATCH') {
      title = JSON.parse(String(init.body)).title
      return response(info(A, title))
    }
    if (url.includes(`/conversations/${A}?`))
      return response({ conversation: info(A, title), items: [], next_cursor: null })
    return response({ items: created ? [info(A, title)] : [], next_cursor: null })
  })
  const router = createAppRouter(createMemoryHistory())
  await router.push('/')
  const page = mount(App, { attachTo: document.body, global: { plugins: [pinia, router] } })
  await flushPromises()
  await page.get('textarea').setValue('原始问题')
  await page.get('form[aria-label="发送消息"]').trigger('submit')
  stream.push(eventFrame('start', { conversation_id: A }))
  await flushPromises()
  expect(page.get('.header-title').text()).toBe('原始问题')
  title = '自动概括的主题'
  stream.push(eventFrame('done', { conversation_id: A, message_id: 'answer', reply: '回答已完成' }))
  await flushPromises()
  await vi.waitFor(() => expect(page.get('.header-title').text()).toBe('自动概括的主题'))
  expect(page.get('.conversation-item').text()).toContain('自动概括的主题')
  expect(page.findAll('article')).toHaveLength(2)
  const chat = useChatStore(),
    selection = modelOptionsData().default_selection
  await page.get('textarea').setValue('不要清空的草稿')
  await page.get('[aria-label="修改会话标题：自动概括的主题"]').trigger('click')
  await flushPromises()
  const dialog = new DOMWrapper(document.querySelector('[role="dialog"]')!)
  await dialog.get('[name="conversation_title"]').setValue('手动定义主题')
  await dialog.get('form[aria-label="修改会话标题"]').trigger('submit')
  await flushPromises()
  expect(page.get('.header-title').text()).toBe('手动定义主题')
  expect(chat.effectiveSelection).toEqual(selection)
  expect((page.get('textarea').element as HTMLTextAreaElement).value).toBe('不要清空的草稿')
  expect(page.findAll('article')).toHaveLength(2)
  expect(fetchMock.mock.calls.filter(([url]) => String(url) === '/api/chat')).toHaveLength(1)
})
