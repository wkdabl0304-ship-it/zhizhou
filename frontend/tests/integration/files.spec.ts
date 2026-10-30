/** 资料库应用集成：真实路由、认证、目录与表单协作，HTTP 只替换公开文件契约。 */
import { beforeEach, expect, it, vi } from 'vitest'
import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'
import { setActivePinia } from 'pinia'
import App from '@/App.vue'
import { createAppRouter } from '@/router'
import { useAuthStore } from '@/features/auth/store'
import { authenticate } from '@tests/support/vitest/auth'
import { createTestPinia } from '@tests/support/vitest/mount'
import { installMediaQuery } from '@tests/support/vitest/browser'
import { deferredResponse, response } from '@tests/support/vitest/http'
import { fileEntry, fileSpace } from '@tests/support/data/files'
import type { FileEntry } from '@/features/files/types'

const fetchMock = vi.fn<typeof fetch>()
let rows: FileEntry[]
let canWrite = true
// 维护最小可变后端模型，让写入后的重读证明整个调用链完成。
beforeEach(() => {
  installMediaQuery()
  rows = []
  canWrite = true
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

/** 为完整应用安装按路径分发的公开协议，不替换业务组件或 Pinia 动作。 */
function installApi(): void {
  fetchMock.mockImplementation(async (input, options) => {
    const url = new URL(String(input), 'http://localhost')
    const space = fileSpace({
      capabilities: canWrite ? ['read', 'upload', 'update', 'delete'] : ['read'],
    })
    if (url.pathname === '/api/files/spaces') return response({ items: [space], next_cursor: null })
    if (url.pathname.endsWith('/entries') && url.pathname.includes('/spaces/')) {
      const parentId = url.searchParams.get('parent_id')
      return response({
        space,
        parent_id: parentId,
        breadcrumbs: parentId
          ? [{ id: parentId, name: rows.find((row) => row.id === parentId)!.name }]
          : [],
        items: rows.filter((row) => row.parent_id === parentId),
        next_cursor: null,
      })
    }
    if (url.pathname.endsWith('/folders')) {
      const body = JSON.parse(options!.body as string)
      const created = fileEntry({
        id: 'folder',
        name: body.name,
        kind: 'folder',
        size_bytes: null,
        parent_id: body.parent_id,
      })
      rows.push(created)
      return response(created)
    }
    if (url.pathname.endsWith('/files') && options?.method === 'POST') {
      const file = (options.body as FormData).get('file') as File
      const created = fileEntry({
        id: `uploaded-${rows.length}`,
        name: file.name,
        size_bytes: file.size,
        parent_id: url.searchParams.get('parent_id'),
      })
      rows.push(created)
      return response(created)
    }
    if (url.pathname.startsWith('/api/files/entries/') && options?.method === 'DELETE') {
      const id = url.pathname.split('/').at(-1)
      rows = rows.filter((row) => row.id !== id)
      return response(null)
    }
    if (url.pathname.startsWith('/api/files/entries/') && options?.method === 'PATCH') {
      const id = url.pathname.split('/').at(-1)
      const body = JSON.parse(options.body as string)
      const entry = rows.find((row) => row.id === id)!
      Object.assign(entry, { name: body.name, version: entry.version + 1 })
      return response(entry)
    }
    return response({ items: [], next_cursor: null })
  })
}

/** 通过真实登录状态进入指定文件路径，保留懒加载和认证守卫。 */
async function open(path = '/files') {
  const pinia = createTestPinia()
  await authenticate(pinia, fetchMock)
  installApi()
  const router = createAppRouter(createMemoryHistory())
  await router.push(path)
  await router.isReady()
  const wrapper = mount(App, { attachTo: document.body, global: { plugins: [pinia, router] } })
  await vi.waitFor(() => expect(wrapper.find('.file-upload').exists()).toBe(canWrite))
  await flushPromises()
  return { wrapper, router, body: new DOMWrapper(document.body) }
}

it('普通账号可从导航进入资料库，创建目录、打开目录并通过历史返回', async () => {
  const { wrapper, router, body } = await open()
  expect(router.currentRoute.value.query.space).toBe('space-personal')
  expect(wrapper.get('h1').text()).toBe('资料库')
  expect(wrapper.find('.files-hero').exists()).toBe(false)
  expect(wrapper.get('.file-empty').text()).toContain('上传文件或拖入此目录')
  expect(wrapper.text()).toContain('单文件上限')
  expect(wrapper.get('[aria-label="资料空间"]').text()).toContain('仅自己可见')
  expect(wrapper.text()).not.toContain('个人珍藏，团队共阅')
  expect(wrapper.get('a[aria-label="资料库"]').attributes('aria-current')).toBe('page')
  expect(wrapper.find('.chat-header').exists()).toBe(false)
  await wrapper
    .findAll('button')
    .find((button) => button.text() === '新建文件夹')!
    .trigger('click')
  await flushPromises()
  await body.get('#file-name').setValue('团队笔记')
  await body.get('#file-action').trigger('submit')
  await flushPromises()
  expect(body.find('[role=dialog]').exists()).toBe(false)
  expect(wrapper.text()).toContain('团队笔记')
  await wrapper.get('.file-folder-link').trigger('click')
  await vi.waitFor(() => expect(router.currentRoute.value.query.folder).toBe('folder'))
  await flushPromises()
  expect(wrapper.get('[aria-label="目录路径"]').text()).toContain('团队笔记')
  router.back()
  await vi.waitFor(() => expect(router.currentRoute.value.query.folder).toBeUndefined())
  await flushPromises()
  expect(wrapper.get('.file-folder-link').text()).toBe('团队笔记')
  expect(body.findAll('[role=alert]')).toHaveLength(0)
})

it('深链接直接恢复目录，改名与删除完成后列表和弹窗同步', async () => {
  rows = [
    fileEntry({ id: 'folder', name: '笔记', kind: 'folder', size_bytes: null }),
    fileEntry({ parent_id: 'folder' }),
  ]
  const { wrapper, router, body } = await open('/files?space=space-personal&folder=folder')
  expect(router.currentRoute.value.query.folder).toBe('folder')
  await wrapper.get('[aria-label="重命名 山海笔记.txt"]').trigger('click')
  await flushPromises()
  await body.get('#file-name').setValue('新资料.txt')
  await body.get('form').trigger('submit')
  await flushPromises()
  expect(wrapper.text()).toContain('新资料.txt')
  await wrapper.get('[aria-label="删除 新资料.txt"]').trigger('click')
  await flushPromises()
  await body.get('form').trigger('submit')
  await flushPromises()
  expect(wrapper.find('.file-table').exists()).toBe(false)
  expect(wrapper.text()).toContain('暂无文件')
  expect(body.find('[role=alert]').exists()).toBe(false)
})

it('权限变化重新读取能力并关闭草稿，资料库仍保留只读浏览', async () => {
  const { wrapper, body } = await open()
  await wrapper
    .findAll('button')
    .find((button) => button.text() === '新建文件夹')!
    .trigger('click')
  await flushPromises()
  expect(body.find('[role=dialog]').exists()).toBe(true)
  canWrite = false
  useAuthStore().user!.grants = [{ permission: 'file:read', scope_type: 'global', scope_id: null }]
  await flushPromises()
  expect(body.find('[role=dialog]').exists()).toBe(false)
  expect(wrapper.find('.file-upload').exists()).toBe(false)
  expect(wrapper.text()).toContain('当前空间可浏览与下载')
})

it('未登录访问文件深链接回登录，并保留原目录返回地址', async () => {
  const pinia = createTestPinia()
  setActivePinia(pinia)
  const router = createAppRouter(createMemoryHistory())
  await router.push('/files?space=space-personal&folder=folder')
  await router.isReady()
  mount(App, { global: { plugins: [pinia, router] } })
  expect(router.currentRoute.value.name).toBe('login')
  expect(router.currentRoute.value.query.redirect).toBe('/files?space=space-personal&folder=folder')
  expect(fetchMock).not.toHaveBeenCalled()
})

it('上传失败刷新目录后保留错误说明，同一目录的同步不卸载上传入口', async () => {
  const { wrapper } = await open()
  const original = wrapper.get('.file-upload').element
  fetchMock.mockResolvedValueOnce(response(null, 413, 41301, '文件超过最新上限'))
  const input = wrapper.get('input[type=file]')
  Object.defineProperty(input.element, 'files', {
    configurable: true,
    value: [new File(['12'], '资料.txt')],
  })
  await input.trigger('change')
  await flushPromises()
  expect(wrapper.get('.file-upload').element).toBe(original)
  expect(wrapper.get('.upload-failures').text()).toContain('资料.txt：文件超过最新上限')
  expect(
    fetchMock.mock.calls.filter(
      ([url, init]) => String(url).endsWith('/files') && init?.method === 'POST',
    ),
  ).toHaveLength(1)
})

/** 构造外部文件拖放数据，仅补齐 jsdom 缺少的 DataTransfer，不替换目录交互。 */
function draggedFile(name: string) {
  return { types: ['Files'], files: [new File(['原件'], name)], items: [], dropEffect: 'none' }
}

it('从系统窗口拖回浏览器时，焦点触发的后台刷新不阻止第一次投递', async () => {
  const { wrapper } = await open()
  const pending = deferredResponse()
  const normal = fetchMock.getMockImplementation()!
  // 仅延迟目录同步，保留真实的上传契约；模拟从资源管理器切回时尚未完成的 GET。
  fetchMock.mockImplementation((input, options) => {
    if (String(input).includes('/api/files/spaces/space-personal/entries'))
      return pending.promise.then((result) => result.clone())
    return normal(input, options)
  })
  window.dispatchEvent(new Event('focus'))
  await flushPromises()
  expect(wrapper.get('.file-directory').attributes('aria-busy')).toBe('true')
  const content = wrapper.get('.file-list-surface')
  const transfer = draggedFile('首次投递.txt')
  await content.trigger('dragover', { dataTransfer: transfer })
  await content.trigger('drop', { dataTransfer: transfer })
  await flushPromises()
  expect(transfer.dropEffect).toBe('copy')
  expect(wrapper.text()).not.toContain('请等待当前操作完成后再拖入文件')
  expect(fetchMock.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(1)
  pending.resolve(
    response({
      space: fileSpace(),
      parent_id: null,
      breadcrumbs: [],
      items: rows,
      next_cursor: null,
    }),
  )
  await flushPromises()
  expect(wrapper.text()).toContain('首次投递.txt')
  expect(wrapper.findAll('[role=alert]')).toHaveLength(0)
})

it('目录空白和文件行接收当前目录上传，文件夹高亮并直接进入接收目录', async () => {
  rows = [fileEntry({ id: 'folder', kind: 'folder', name: '收件夹', size_bytes: null })]
  const { wrapper, router } = await open()
  expect(wrapper.text()).not.toContain('把资料放在这里')
  const content = wrapper.get('.file-list-surface')
  const rootTransfer = draggedFile('根目录.txt')
  await content.trigger('dragover', { dataTransfer: rootTransfer })
  expect(content.classes()).toContain('is-dragging')
  expect(rootTransfer.dropEffect).toBe('copy')
  await content.trigger('drop', { dataTransfer: rootTransfer })
  await flushPromises()
  expect(wrapper.text()).toContain('根目录.txt')
  expect(
    String(
      fetchMock.mock.calls.find(
        ([url, init]) => String(url).endsWith('/files') && init?.method === 'POST',
      )![0],
    ),
  ).not.toContain('parent_id')
  const row = wrapper.get('[data-folder-id="folder"]')
  const folderTransfer = draggedFile('夹内资料.txt')
  await row.get('td').trigger('dragover', { dataTransfer: folderTransfer })
  expect(row.classes()).toContain('is-drop-target')
  expect(content.classes()).not.toContain('is-dragging')
  expect(wrapper.text()).toContain('松开以上传到「收件夹」')
  await row.get('td').trigger('drop', { dataTransfer: folderTransfer })
  await flushPromises()
  expect(router.currentRoute.value.query.folder).toBe('folder')
  expect(wrapper.text()).toContain('夹内资料.txt')
  expect(wrapper.get('.file-breadcrumbs').text()).toContain('收件夹')
  expect(
    fetchMock.mock.calls.some(
      ([url, init]) => String(url).endsWith('/files?parent_id=folder') && init?.method === 'POST',
    ),
  ).toBe(true)
  expect(wrapper.findAll('.is-drop-target')).toHaveLength(0)
})

it('只读目录拒绝文件拖入，普通文本拖动不触发上传或高亮', async () => {
  canWrite = false
  const { wrapper } = await open()
  const content = wrapper.get('.file-list-surface')
  const external = draggedFile('无权限.txt')
  await content.trigger('dragover', { dataTransfer: external })
  expect(external.dropEffect).toBe('none')
  expect(content.classes()).not.toContain('is-dragging')
  await content.trigger('drop', { dataTransfer: external })
  await flushPromises()
  expect(wrapper.get('[role=alert]').text()).toContain('没有上传权限')
  await content.trigger('dragover', { dataTransfer: { types: ['text/plain'] } })
  await content.trigger('drop', { dataTransfer: { types: ['text/plain'] } })
  expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(0)
})

it('整文件夹拖入明确报错而不误存为空文件，离开列表清除拖放高亮', async () => {
  const { wrapper } = await open()
  const content = wrapper.get('.file-list-surface')
  const external = {
    ...draggedFile('本地文件夹'),
    items: [{ webkitGetAsEntry: () => ({ isDirectory: true }) }],
  }
  await content.trigger('dragover', { dataTransfer: external })
  await content.trigger('dragleave', { relatedTarget: document.body })
  expect(content.classes()).not.toContain('is-dragging')
  await content.trigger('drop', { dataTransfer: external })
  expect(wrapper.get('[role=alert]').text()).toContain('暂不支持上传整个文件夹')
  expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(0)
  const input = wrapper.get('input[type=file]')
  Object.defineProperty(input.element, 'files', {
    configurable: true,
    value: [new File(['原件'], '修正后的资料.txt')],
  })
  await input.trigger('change')
  await flushPromises()
  expect(wrapper.text()).toContain('修正后的资料.txt')
  expect(wrapper.findAll('[role=alert]')).toHaveLength(0)
})
