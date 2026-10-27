/** 公共弹窗和标题行为回归：配置化布局、初始焦点、忙碌保护、确认反馈和页面语义。 */
import { expect, it, vi } from 'vitest'
import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import UiModal from '../../components/ui/UiModal.vue'
import UiConfirmDialog from '../../components/ui/UiConfirmDialog.vue'
import UiPageHeader from '../../components/ui/UiPageHeader.vue'

it('弹窗支持尺寸、固定底栏和初始焦点，保存期间拦截 Esc 与关闭按钮', async () => {
  const close = vi.fn<(value: boolean) => void>()
  const host = mount(UiModal, {
    attachTo: document.body,
    props: {
      open: true,
      title: '编辑记录',
      size: 'lg',
      busy: true,
      initialFocus: 'input',
      'onUpdate:open': close,
    },
    slots: { default: '<input aria-label="名称" />', footer: '<button>保存记录</button>' },
  })
  await flushPromises()
  const page = new DOMWrapper(document.body)
  await vi.waitFor(() => expect(document.activeElement).toBe(page.get('input').element))
  expect(page.get('[role="dialog"]').attributes('style')).toContain('680px')
  expect(page.get('.ui-modal-footer').text()).toBe('保存记录')
  document.dispatchEvent(
    new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }),
  )
  await page.get('[aria-label="关闭"]').trigger('click')
  await flushPromises()
  expect(close).not.toHaveBeenCalled()
  await host.setProps({ busy: false })
  document.dispatchEvent(
    new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }),
  )
  await flushPromises()
  expect(close).toHaveBeenCalledOnce()
  await page.get('[aria-label="关闭"]').trigger('click')
  expect(close).toHaveBeenLastCalledWith(false)
})

it('常驻弹窗每次打开记录新的入口，外部关闭策略可配置', async () => {
  const Host = defineComponent({
    components: { UiModal },
    setup: () => ({ open: ref(false) }),
    template:
      '<main><button id="a" @click="open = true">入口一</button><button id="b" @click="open = true">入口二</button><UiModal v-model:open="open" title="常驻弹窗" :close-on-escape="false"><input /></UiModal></main>',
  })
  const host = mount(Host, { attachTo: document.body })
  for (const id of ['a', 'b']) {
    const trigger = host.get<HTMLButtonElement>('#' + id)
    trigger.element.focus()
    await trigger.trigger('click')
    await flushPromises()
    document.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }),
    )
    await flushPromises()
    expect(document.querySelector('[role="dialog"]')).not.toBeNull()
    await new DOMWrapper(document.querySelector('[aria-label="关闭"]')!).trigger('click')
    await flushPromises()
    await vi.waitFor(() => expect(document.activeElement).toBe(trigger.element))
  }
})

it('确认弹窗默认聚焦取消，支持错误重试和业务控制关闭', async () => {
  const confirm = vi.fn<() => void>()
  const host = mount(UiConfirmDialog, {
    attachTo: document.body,
    props: { open: true, title: '删除记录？', confirmLabel: '确定移除', onConfirm: confirm },
  })
  await flushPromises()
  const page = new DOMWrapper(document.body)
  await vi.waitFor(() =>
    expect(document.activeElement).toBe(page.get('[data-confirm-cancel]').element),
  )
  await page.findAll('button').at(-1)!.trigger('click')
  expect(confirm).toHaveBeenCalledOnce()
  expect(page.get('[role="dialog"]').text()).toContain('删除记录？')
  await host.setProps({ busy: true, error: '稍后重试' })
  await page.findAll('button').at(-1)!.trigger('click')
  expect(confirm).toHaveBeenCalledOnce()
  expect(page.get('[role="alert"]').text()).toBe('稍后重试')
})

it('页面标题支持级别、眉题、说明、操作插槽和焦点恢复', async () => {
  const host = mount(UiPageHeader, {
    attachTo: document.body,
    props: {
      title: '资料管理',
      eyebrow: 'WORKSPACE',
      description: '组织资料',
      level: 2,
      size: 'lg',
      editable: true,
    },
    slots: { actions: '<button>新建</button>' },
  })
  expect(host.get('h2').text()).toBe('资料管理')
  expect(host.text()).toContain('WORKSPACE')
  expect(host.text()).toContain('组织资料')
  expect(host.get('button').text()).toBe('新建')
  await host.get('h2').trigger('dblclick')
  expect(host.emitted('titleDblclick')).toHaveLength(1)
  host.vm.focus()
  expect(document.activeElement).toBe(host.get('h2').element)
})
