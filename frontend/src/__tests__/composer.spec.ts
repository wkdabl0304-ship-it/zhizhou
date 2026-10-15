/** 输入区回归：以原生事件验证发送约束和中文输入法，不复制 Reka 的内部测试。 */
import { afterEach, describe, expect, it } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { TooltipProvider } from 'reka-ui'
import { defineComponent } from 'vue'
import ChatComposer from '@/components/chat/ChatComposer.vue'

const wrappers: VueWrapper[] = []
/** 挂载输入区并提供真实 Tooltip 上下文；DOM 在每项测试后统一卸载。 */
function createComposer(disabled = false) {
  const Host = defineComponent({
    components: { ChatComposer, TooltipProvider },
    // 固定禁用参数用于检查业务发送约束，其他行为使用真实组件。
    setup: () => ({ disabled }),
    template: '<TooltipProvider><ChatComposer :disabled="disabled" /></TooltipProvider>',
  })
  const wrapper = mount(Host, { attachTo: document.body })
  wrappers.push(wrapper)
  return wrapper.findComponent(ChatComposer)
}

// 清理 Vue 实例与 Portal，避免焦点和 Tooltip 状态跨测试残留。
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  document.body.innerHTML = ''
})

describe('聊天输入区', () => {
  // 空白与 Shift+Enter 保留编辑，普通 Enter 才发送并清空。
  it('阻止空白发送，保留换行意图，发送后清空草稿', async () => {
    const composer = createComposer()
    const textarea = composer.get('textarea')
    expect(composer.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    await textarea.setValue('  \n ')
    await textarea.trigger('keydown', { key: 'Enter' })
    expect(composer.emitted('send')).toBeUndefined()
    await textarea.setValue('  工作计划  ')
    await textarea.trigger('keydown', { key: 'Enter', shiftKey: true })
    expect(composer.emitted('send')).toBeUndefined()
    await textarea.trigger('keydown', { key: 'Enter' })
    expect(composer.emitted('send')).toEqual([['工作计划']])
    expect((textarea.element as HTMLTextAreaElement).value).toBe('')
  })

  // 覆盖组合生命周期及浏览器兼容分支，防止选词回车意外发送。
  it('中文输入法选词和兼容事件不会触发发送', async () => {
    const composer = createComposer()
    const textarea = composer.get('textarea')
    await textarea.setValue('中文')
    await textarea.trigger('compositionstart')
    await textarea.trigger('keydown', { key: 'Enter' })
    await textarea.trigger('compositionend')
    await textarea.trigger('keydown', { key: 'Enter', isComposing: true })
    await textarea.trigger('keydown', { key: 'Enter', keyCode: 229 })
    expect(composer.emitted('send')).toBeUndefined()
    await textarea.trigger('keydown', { key: 'Enter' })
    expect(composer.emitted('send')).toEqual([['中文']])
  })

  // 禁用态既约束按钮，也约束脚本式表单提交路径。
  it('禁用时不发送，原生表单提交正常发送', async () => {
    const disabled = createComposer(true)
    await disabled.get('textarea').setValue('不可发送')
    await disabled.get('form').trigger('submit')
    expect(disabled.emitted('send')).toBeUndefined()
    const enabled = createComposer()
    await enabled.get('textarea').setValue('点击发送')
    await enabled.get('form').trigger('submit')
    expect(enabled.emitted('send')).toEqual([['点击发送']])
  })
})
