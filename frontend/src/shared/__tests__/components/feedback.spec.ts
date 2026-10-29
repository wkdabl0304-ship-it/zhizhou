/** 公共反馈与标签：验证静态语义、错误可访问性、重试边界和属性透传。 */
import { expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import UiTag from '@/shared/components/ui/UiTag.vue'
import UiFeedback from '@/shared/components/ui/UiFeedback.vue'

it('标签保留文本和语义色，不把身份或状态误当成按钮或实时通知', () => {
  const tag = mount(UiTag, { props: { tone: 'brand', dot: true }, slots: { default: '本人' } })
  expect(tag.text()).toBe('本人')
  expect(tag.element.tagName).toBe('SPAN')
  expect(tag.attributes('role')).toBeUndefined()
  expect(tag.attributes('tabindex')).toBeUndefined()
  expect(tag.get('.ui-tag-dot').attributes('aria-hidden')).toBe('true')
})

it('标签默认采用小尺寸，可按页面密度切换四档尺寸并保留内容和语义色', async () => {
  const tag = mount(UiTag, { props: { tone: 'brand', dot: true }, slots: { default: '已启用' } })
  expect(tag.classes()).toContain('ui-tag--sm')
  for (const size of ['xs', 'sm', 'md', 'lg'] as const) {
    await tag.setProps({ size })
    expect(tag.classes()).toContain(`ui-tag--${size}`)
    expect(tag.classes()).toContain('ui-tag--brand')
    expect(tag.text()).toBe('已启用')
    expect(tag.findAll('.ui-tag-dot')).toHaveLength(1)
    expect(tag.attributes('tabindex')).toBeUndefined()
  }
  await tag.setProps({ size: undefined })
  expect(tag.classes()).toContain('ui-tag--sm')
})

it('失败反馈透传字段 ID，重试只发事件且等待时禁止重复操作', async () => {
  const retry = vi.fn<() => void>()
  const feedback = mount(UiFeedback, {
    props: { title: '加载失败', message: '网络连接中断', retryLabel: '重试目录', onRetry: retry },
    attrs: { id: 'field-error' },
  })
  expect(feedback.attributes('role')).toBe('alert')
  expect(feedback.attributes('id')).toBe('field-error')
  expect(feedback.text()).toContain('网络连接中断')
  await feedback.get('button').trigger('click')
  expect(retry).toHaveBeenCalledOnce()
  await feedback.setProps({ busy: true })
  await feedback.get('button').trigger('click')
  expect(retry).toHaveBeenCalledOnce()
  expect(feedback.get('button').attributes('aria-busy')).toBe('true')
})

it('紧凑字段反馈没有多余操作入口，内容插槽可以补充修正说明', () => {
  const feedback = mount(UiFeedback, {
    props: { compact: true },
    slots: { default: '密码至少 8 个字符' },
  })
  expect(feedback.get('[role="alert"]').text()).toBe('密码至少 8 个字符')
  expect(feedback.find('button').exists()).toBe(false)
})
