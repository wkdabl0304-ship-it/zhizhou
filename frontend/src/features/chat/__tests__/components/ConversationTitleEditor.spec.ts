/** 标题弹窗回归：规范化、字符边界、自动更新草稿隔离、失败重试与键盘取消。 */
import { expect, it, vi } from 'vitest'
import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import ConversationTitleEditor from '../../components/ConversationTitleEditor.vue'
import { normalizeTitle, titleIssue } from '../../titles'

it('空白处理与后端一致，按 Unicode 字符而非 UTF-16 计数', () => {
  expect(normalizeTitle(' \u0085甲\u001c\t乙\n')).toBe('甲 乙')
  expect(normalizeTitle('\ufeff甲')).toBe('\ufeff甲')
  expect(titleIssue('🚣'.repeat(100))).toBe('')
  expect(titleIssue('🚣'.repeat(101))).toContain('100')
})

it('输入时保留草稿，自动标题更新不覆盖草稿，空白和超长标题不提交', async () => {
  const save = vi.fn<(title: string) => Promise<boolean>>(async () => true)
  const host = mount(ConversationTitleEditor, {
    props: { title: '原标题', save },
    attachTo: document.body,
  })
  await flushPromises()
  const page = new DOMWrapper(document.body)
  await vi.waitFor(() => expect(document.activeElement).toBe(page.get('input').element))
  await page.get('input').setValue('用户输入')
  await host.setProps({ title: '自动更新的标题' })
  expect((page.get('input').element as HTMLInputElement).value).toBe('用户输入')
  await page.get('input').setValue('  \n')
  await page.get('form').trigger('submit')
  expect(page.get('[role="alert"]').text()).toContain('请输入')
  await page.get('input').setValue('🚣'.repeat(101))
  await page.get('form').trigger('submit')
  expect(page.get('[role="alert"]').text()).toContain('100')
  expect(save).not.toHaveBeenCalled()
  host.unmount()
})

it('失败保留输入并显示服务端提示，重试按规范化标题保存', async () => {
  const save = vi
    .fn<(title: string) => Promise<boolean>>()
    .mockResolvedValueOnce(false)
    .mockResolvedValueOnce(true)
  const host = mount(ConversationTitleEditor, {
    props: { title: '原标题', save, saveError: '会话不存在' },
  })
  await flushPromises()
  const page = new DOMWrapper(document.body)
  await page.get('input').setValue('  新的\t标题  ')
  await page.get('form').trigger('submit')
  await flushPromises()
  expect(page.get('[role="alert"]').text()).toBe('会话不存在')
  expect((page.get('input').element as HTMLInputElement).value).toBe('  新的\t标题  ')
  expect(host.emitted('saved')).toBeUndefined()
  await page.get('form').trigger('submit')
  await flushPromises()
  expect(save).toHaveBeenLastCalledWith('新的 标题')
  expect(host.emitted('saved')).toHaveLength(1)
  host.unmount()
})

it('保存期间禁止重复提交与取消，Esc 仅取消未提交编辑', async () => {
  let resolve!: (value: boolean) => void
  const save = vi.fn<(title: string) => Promise<boolean>>(
    () =>
      new Promise<boolean>((done) => {
        resolve = done
      }),
  )
  const host = mount(ConversationTitleEditor, {
    props: { title: '原标题', save },
    attachTo: document.body,
  })
  await flushPromises()
  const page = new DOMWrapper(document.body)
  await page.get('form').trigger('submit')
  await page.get('form').trigger('submit')
  await page.get('input').trigger('keydown', { key: 'Escape' })
  expect(host.emitted('cancel')).toBeUndefined()
  expect(save).toHaveBeenCalledTimes(1)
  expect(page.get('input').attributes('disabled')).toBeDefined()
  resolve(false)
  await flushPromises()
  await page.get('input').trigger('keydown', { key: 'Escape' })
  expect(host.emitted('cancel')).toHaveLength(1)
  host.unmount()
})

it('中文输入法确认和取消组词不触发保存或退出编辑', async () => {
  const save = vi.fn<(title: string) => Promise<boolean>>(async () => true)
  const host = mount(ConversationTitleEditor, {
    props: { title: '原标题', save },
    attachTo: document.body,
  })
  await flushPromises()
  const page = new DOMWrapper(document.body)
  const enter = new KeyboardEvent('keydown', {
    key: 'Enter',
    isComposing: true,
    bubbles: true,
    cancelable: true,
  })
  page.get('input').element.dispatchEvent(enter)
  expect(enter.defaultPrevented).toBe(true)
  await page.get('input').trigger('keydown', { key: 'Escape', isComposing: true })
  expect(host.emitted('cancel')).toBeUndefined()
  expect(save).not.toHaveBeenCalled()
  host.unmount()
})
