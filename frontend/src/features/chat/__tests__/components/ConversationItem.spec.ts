/** 会话条目回归：区分鼠标双击与普通选择，触发器归属和键盘入口不依赖状态层。 */
import { expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ConversationItem from '../../components/ConversationItem.vue'

it('双击改名取消尚未执行的单击导航，键盘选择仍立即执行', async () => {
  vi.useFakeTimers()
  const page = mount(ConversationItem, { props: { title: '话题', active: true, renamable: true } })
  const title = page.get('.conversation-item')
  title.element.dispatchEvent(new MouseEvent('click', { detail: 1, bubbles: true }))
  title.element.dispatchEvent(new MouseEvent('click', { detail: 2, bubbles: true }))
  await title.trigger('dblclick')
  await vi.advanceTimersByTimeAsync(400)
  expect(page.emitted('select')).toBeUndefined()
  expect(page.emitted('rename')?.[0]).toEqual([title.element])
  title.element.dispatchEvent(new MouseEvent('click', { detail: 0, bubbles: true }))
  expect(page.emitted('select')).toHaveLength(1)
})

it('普通鼠标单击只导航一次，卸载后释放尚未执行的导航', async () => {
  vi.useFakeTimers()
  const selected = vi.fn<() => void>()
  const page = mount(ConversationItem, {
    props: { title: '话题', active: false, renamable: true, onSelect: selected },
  })
  page
    .get('.conversation-item')
    .element.dispatchEvent(new MouseEvent('click', { detail: 1, bubbles: true }))
  await vi.advanceTimersByTimeAsync(300)
  expect(selected).toHaveBeenCalledOnce()
  page
    .get('.conversation-item')
    .element.dispatchEvent(new MouseEvent('click', { detail: 1, bubbles: true }))
  expect(vi.getTimerCount()).toBe(1)
  page.unmount()
  expect(vi.getTimerCount()).toBe(0)
  await vi.advanceTimersByTimeAsync(300)
  expect(selected).toHaveBeenCalledOnce()
})
