/** 文件组件行为测试：覆盖能力入口、名称校验、冻结版本、上传失败与策略边界。 */
import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import { authenticate } from '@tests/support/vitest/auth'
import { createTestPinia } from '@tests/support/vitest/mount'
import { deferredResponse, response } from '@tests/support/vitest/http'
import { fileEntry, filePolicy, fileSpace } from '@tests/support/data/files'
import FileActionDialog from '../components/FileActionDialog.vue'
import FileTable from '../components/FileTable.vue'
import FileUpload from '../components/FileUpload.vue'
import UploadLimitDialog from '../components/UploadLimitDialog.vue'
import type { FileAction } from '../types'
import { chooseSelect } from '@tests/support/vitest/controls'

const fetchMock = vi.fn<typeof fetch>()
// 真实公共控件与认证状态参与测试，仅替换 HTTP。
beforeEach(async () => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  await authenticate(createTestPinia(), fetchMock)
})

/** 挂载文件操作弹窗，用 Portal 的用户可见 DOM 触发表单。 */
async function dialog(action: FileAction) {
  const wrapper = mount(FileActionDialog, { props: { action }, attachTo: document.body })
  await flushPromises()
  return { wrapper, body: new DOMWrapper(document.body) }
}

/** 将文件选择注入原生 input，随后使用真实 change 流程上传。 */
async function choose(wrapper: ReturnType<typeof mount>, files: File[]) {
  const input = wrapper.get('input[type=file]')
  Object.defineProperty(input.element, 'files', { configurable: true, value: files })
  await input.trigger('change')
  await flushPromises()
}

it('只读空间保留文件下载和目录进入，维护能力分别控制按钮', async () => {
  const folder = fileEntry({ id: 'folder', kind: 'folder', name: '笔记', size_bytes: null })
  const wrapper = mount(FileTable, {
    props: {
      entries: [fileEntry(), folder],
      space: fileSpace({ capabilities: ['read'] }),
      downloading: [],
    },
  })
  expect(wrapper.findAll('button')).toHaveLength(2)
  await wrapper.get('.file-folder-link').trigger('click')
  expect(wrapper.emitted('folder')?.[0]).toEqual([folder])
  await wrapper.get('[aria-label="下载 山海笔记.txt"]').trigger('click')
  expect(wrapper.emitted('download')).toHaveLength(1)
  await wrapper.setProps({
    space: fileSpace({ capabilities: ['read', 'update'] }),
    downloading: ['entry-1'],
  })
  expect(wrapper.findAll('[aria-label^="重命名"]')).toHaveLength(2)
  expect(wrapper.find('[aria-label^="删除"]').exists()).toBe(false)
  expect(wrapper.get('[aria-label^="下载"]').attributes('disabled')).toBeDefined()
})

it('单击文件夹图标、名称外空白或其他列进入一次，操作按钮与文件行不会误导航', async () => {
  const folder = fileEntry({ id: 'folder', kind: 'folder', name: '笔记', size_bytes: null })
  const wrapper = mount(FileTable, {
    props: { entries: [folder, fileEntry()], space: fileSpace(), downloading: [] },
  })
  const row = wrapper.get('[data-folder-id="folder"]')
  await row.get('.file-type-icon svg').trigger('click')
  await row.get('td').trigger('click')
  await row.get('.file-date-column').trigger('click')
  await row.get('.file-folder-link').trigger('click')
  expect(wrapper.emitted('folder')).toHaveLength(4)
  await row.get('[aria-label="重命名 笔记"]').trigger('click')
  await row.get('[aria-label="删除 笔记"]').trigger('click')
  await row.get('.file-actions-column').trigger('click')
  await wrapper.get('[aria-label="下载 山海笔记.txt"]').trigger('click')
  await wrapper.get('tbody tr:not([data-folder-id]) td').trigger('click')
  expect(wrapper.emitted('folder')).toHaveLength(4)
  expect(wrapper.emitted('rename')?.[0]).toEqual([folder])
  expect(wrapper.emitted('delete')?.[0]).toEqual([folder])
  expect(wrapper.emitted('download')).toHaveLength(1)
})

it('非法名称不发请求，提交中的目录创建不能重复执行', async () => {
  const pending = deferredResponse()
  fetchMock.mockReturnValueOnce(pending.promise)
  const { wrapper, body } = await dialog({ kind: 'create', space: fileSpace(), parentId: 'parent' })
  await body.get('input').setValue('../资料')
  await body.get('form').trigger('submit')
  expect(fetchMock).not.toHaveBeenCalled()
  expect(body.text()).toContain('路径分隔符')
  await body.get('input').setValue(' 文档 ')
  await body.get('form').trigger('submit')
  await body.get('form').trigger('submit')
  expect(fetchMock).toHaveBeenCalledOnce()
  expect(JSON.parse(fetchMock.mock.calls[0]![1]!.body as string)).toEqual({
    name: '文档',
    parent_id: 'parent',
  })
  pending.resolve(response(fileEntry({ kind: 'folder', size_bytes: null, name: '文档' })))
  await flushPromises()
  expect(wrapper.emitted('saved')).toHaveLength(1)
  expect(body.find('[role=alert]').exists()).toBe(false)
})

it('重命名冲突保留输入并阻止旧版本重复提交，名称冲突允许修正', async () => {
  const { wrapper, body } = await dialog({
    kind: 'rename',
    space: fileSpace(),
    entry: fileEntry({ version: 5 }),
  })
  fetchMock.mockResolvedValueOnce(response(null, 409, 40909, '名称已存在'))
  await body.get('input').setValue('另一个名称')
  await body.get('form').trigger('submit')
  await flushPromises()
  expect(body.text()).toContain('名称已存在')
  expect(body.get('input').attributes('disabled')).toBeUndefined()
  fetchMock.mockResolvedValueOnce(response(null, 409, 40910, '版本冲突'))
  await body.get('input').setValue('新名')
  await body.get('form').trigger('submit')
  await flushPromises()
  expect((body.get('input').element as HTMLInputElement).value).toBe('新名')
  expect(body.text()).toContain('重新查看后再操作')
  expect(body.get('input').attributes('disabled')).toBeDefined()
  await body.get('form').trigger('submit')
  expect(fetchMock).toHaveBeenCalledTimes(2)
  expect(wrapper.emitted('saved')).toBeUndefined()
})

it('删除目录明确递归后果且使用冻结版本，存储错误保留弹窗', async () => {
  fetchMock.mockResolvedValueOnce(response(null, 500, 50004, '存储不可用'))
  const { wrapper, body } = await dialog({
    kind: 'delete',
    space: fileSpace(),
    entry: fileEntry({ kind: 'folder', size_bytes: null, version: 4 }),
  })
  expect(body.text()).toContain('所有下级资料将一并删除')
  await body.get('form').trigger('submit')
  await flushPromises()
  expect(fetchMock.mock.calls[0]![0]).toContain('version=4')
  expect(body.text()).toContain('存储不可用')
  expect(wrapper.emitted('saved')).toBeUndefined()
})

it('工具栏按钮选择文件并清空原生值，上传中保持焦点且可主动中止', async () => {
  const wrapper = mount(FileUpload, { props: { busy: false }, attachTo: document.body })
  const trigger = wrapper.get('button').element
  trigger.focus()
  const file = new File(['原件'], '笔记.txt')
  await choose(wrapper, [file])
  expect(wrapper.emitted('files')?.[0]).toEqual([[file]])
  expect((wrapper.get('input').element as HTMLInputElement).value).toBe('')
  await wrapper.setProps({ busy: true })
  expect(document.activeElement).toBe(trigger)
  await wrapper.get('button').trigger('click')
  expect(wrapper.emitted('cancel')).toHaveLength(1)
  expect(fetchMock).not.toHaveBeenCalled()
  expect(wrapper.text()).not.toContain('把资料放在这里')
})
it('中文名称组词确认不提前提交，组成结束后保存完整文本', async () => {
  const { body } = await dialog({ kind: 'create', space: fileSpace(), parentId: null })
  const input = body.get('input')
  await input.trigger('compositionstart')
  await input.setValue('项目笔记')
  const enter = new KeyboardEvent('keydown', {
    key: 'Enter',
    isComposing: true,
    bubbles: true,
    cancelable: true,
  })
  input.element.dispatchEvent(enter)
  expect(enter.defaultPrevented).toBe(true)
  await body.get('form').trigger('submit')
  expect(fetchMock).not.toHaveBeenCalled()
  await input.trigger('compositionend')
  fetchMock.mockResolvedValueOnce(
    response(fileEntry({ kind: 'folder', size_bytes: null, name: '项目笔记' })),
  )
  await body.get('form').trigger('submit')
  await flushPromises()
  expect(JSON.parse(fetchMock.mock.calls[0]![1]!.body as string).name).toBe('项目笔记')
})

it('个人上传策略默认显示 MB，可选择单位和输入小数，并精确提交最新版本', async () => {
  fetchMock.mockResolvedValueOnce(response(filePolicy()))
  const wrapper = mount(UploadLimitDialog, {
    props: { space: fileSpace() },
    attachTo: document.body,
  })
  await flushPromises()
  const body = new DOMWrapper(document.body)
  expect(body.text()).toContain('所有用户的个人空间')
  expect((body.get('#upload-limit-amount').element as HTMLInputElement).value).toBe('100')
  expect(body.get('[role=combobox]').text()).toContain('MB')
  for (const invalid of ['0', '-1', '1e3', '1048577', '0.0000001']) {
    await body.get('input').setValue(invalid)
    await body.get('form').trigger('submit')
  }
  expect(fetchMock).toHaveBeenCalledOnce()
  fetchMock.mockResolvedValueOnce(
    response({ ...filePolicy(), max_file_size_bytes: 1536, version: 2 }),
  )
  await chooseSelect(body.get('[role=combobox]'), 'KB')
  await body.get('#upload-limit-amount').setValue('1.5')
  await body.get('form').trigger('submit')
  await flushPromises()
  expect(JSON.parse(fetchMock.mock.calls[1]![1]!.body as string)).toEqual({
    max_file_size_bytes: 1536,
    version: 1,
  })
  expect(wrapper.emitted('saved')).toHaveLength(1)
})

it('上传策略读取失败可重试，版本冲突保留草稿并禁止重复覆盖', async () => {
  fetchMock.mockResolvedValueOnce(response(null, 500, 50004, '策略暂不可用'))
  const wrapper = mount(UploadLimitDialog, {
    props: { space: fileSpace() },
    attachTo: document.body,
  })
  await flushPromises()
  const body = new DOMWrapper(document.body)
  expect(body.text()).toContain('策略暂不可用')
  fetchMock.mockResolvedValueOnce(response(filePolicy()))
  await body
    .findAll('button')
    .find((button) => button.text() === '重新读取策略')!
    .trigger('click')
  await flushPromises()
  await body.get('input').setValue('2048')
  fetchMock.mockResolvedValueOnce(response(null, 409, 40911, '策略版本冲突'))
  await body.get('form').trigger('submit')
  await flushPromises()
  expect(body.findAll('[role=alert]')).toHaveLength(1)
  expect(body.text()).toContain('重新查看后再操作')
  expect((body.get('input').element as HTMLInputElement).value).toBe('2048')
  await body.get('form').trigger('submit')
  expect(fetchMock).toHaveBeenCalledTimes(3)
  expect(wrapper.emitted('saved')).toBeUndefined()
  expect(wrapper.emitted('conflict')).toHaveLength(1)
})

it('历史策略用简短小数回显，未改动保存仍提交原始精确上限', async () => {
  const policy = { ...filePolicy(), max_file_size_bytes: 1048577 }
  fetchMock.mockResolvedValueOnce(response(policy)).mockResolvedValueOnce(response(policy))
  mount(UploadLimitDialog, { props: { space: fileSpace() }, attachTo: document.body })
  await flushPromises()
  const body = new DOMWrapper(document.body)
  expect((body.get('#upload-limit-amount').element as HTMLInputElement).value).toBe('1')
  expect(body.get('[role=combobox]').text()).toContain('MB')
  await body.get('form').trigger('submit')
  await flushPromises()
  expect(JSON.parse(fetchMock.mock.calls[1]![1]!.body as string).max_file_size_bytes).toBe(1048577)
})
