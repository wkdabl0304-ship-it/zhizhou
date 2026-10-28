/** 基础表单控件测试：验证原生输入、标签点击、下拉空值、禁用与弹窗内焦点交互。 */
import { beforeEach, describe, expect, it } from 'vitest'
import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import UiInput from '../../components/ui/UiInput.vue'
import UiCheckbox from '../../components/ui/UiCheckbox.vue'
import UiSelect from '../../components/ui/UiSelect.vue'
import UiModal from '../../components/ui/UiModal.vue'
import { chooseSelect, installSelectBrowser } from '@tests/support/vitest/controls'

// jsdom 没有滚动布局，只补齐 Reka 在选项聚焦时调用的浏览器方法。
beforeEach(installSelectBrowser)

describe('通用输入框', () => {
  it('输入法确认前不更新模型，确认后提交完整中文内容', async () => {
    const page = mount(UiInput, { props: { modelValue: '' } })
    const input = page.get('input')
    await input.trigger('compositionstart')
    input.element.value = '山海'
    await input.trigger('input')
    expect(page.emitted('update:modelValue')).toBeUndefined()
    await input.trigger('compositionend')
    expect(page.emitted('update:modelValue')?.[0]).toEqual(['山海'])
  })

  it('受控 value 更新不会被内部编辑状态遮住', async () => {
    const Host = defineComponent({
      components: { UiInput },
      setup() {
        return { value: ref(1024) }
      },
      template: '<UiInput :value="value" />',
    })
    const page = mount(Host)
    await page.get('input').setValue('2048')
    page.vm.value = 4096
    await flushPromises()
    expect(page.get('input').element.value).toBe('4096')
  })
  it('输入不裁剪空格，原生属性与错误说明落到实际输入节点', async () => {
    const page = mount(UiInput, {
      props: { modelValue: '', disabled: false },
      attrs: {
        name: 'password',
        type: 'password',
        autocomplete: 'new-password',
        'aria-label': '新密码',
        'aria-invalid': true,
        'aria-describedby': 'issue',
      },
    })
    await page.get('input').setValue(' password ')
    expect(page.emitted('update:modelValue')?.[0]).toEqual([' password '])
    expect(page.get('input').attributes()).toMatchObject({
      name: 'password',
      type: 'password',
      'aria-describedby': 'issue',
    })
    expect(page.attributes('data-invalid')).toBe('true')
    await page.setProps({ disabled: true })
    expect(page.get('input').element.disabled).toBe(true)
  })

  it('数值修饰符保持数字类型，前后缀不影响输入模型', async () => {
    const Host = defineComponent({
      components: { UiInput },
      setup() {
        return { value: ref(12) }
      },
      template:
        '<UiInput v-model.number="value" type="number" aria-label="预算"><template #prefix>预算</template><template #suffix>tokens</template></UiInput>',
    })
    const page = mount(Host)
    await page.get('input').setValue('24')
    expect(page.vm.value).toBe(24)
    expect(page.text()).toContain('tokens')
  })

  it('公开聚焦和选中方法操作真实文本输入，供标题弹窗替换原有内容', () => {
    const page = mount(UiInput, {
      attachTo: document.body,
      props: { modelValue: '原有标题' },
    })
    const input = page.get('input').element
    page.vm.focus()
    expect(document.activeElement).toBe(input)
    page.vm.select()
    expect(input.selectionStart).toBe(0)
    expect(input.selectionEnd).toBe('原有标题'.length)
    expect(input.value).toBe('原有标题')
  })
})

describe('通用复选框', () => {
  it('点击整行标签切换，原生表单值保持真实布尔选择', async () => {
    const Host = defineComponent({
      components: { UiCheckbox },
      setup() {
        return { selected: ref(false) }
      },
      template:
        '<form><UiCheckbox v-model="selected" name="unassigned">仅无部门</UiCheckbox></form>',
    })
    const page = mount(Host, { attachTo: document.body })
    await page.get('label').trigger('click')
    expect(page.vm.selected).toBe(true)
    expect(new FormData(page.get('form').element).has('unassigned')).toBe(true)
    await page.get('input').setValue(false)
    expect(page.vm.selected).toBe(false)
  })

  it('禁用复选框保留不可操作语义', () => {
    const page = mount(UiCheckbox, {
      props: { disabled: true },
      attrs: { 'aria-label': '仅无部门' },
    })
    expect(page.get('input').element.disabled).toBe(true)
    expect(page.get('input').attributes('aria-label')).toBe('仅无部门')
  })
})

describe('通用下拉框', () => {
  it('弹窗内选择后更新业务值，支持空值并提交真实表单值', async () => {
    const Host = defineComponent({
      components: { UiModal, UiSelect },
      setup() {
        return {
          selected: ref(''),
          options: [
            { value: '', label: '全部状态' },
            { value: 'false', label: '已停用' },
            { value: 'blocked', label: '不可用', disabled: true },
          ],
        }
      },
      template:
        '<UiModal :open="true" title="筛选"><form><label>账号状态<UiSelect v-model="selected" name="active" :options="options" aria-label="账号状态" /></label></form></UiModal>',
    })
    const page = mount(Host, { attachTo: document.body }),
      body = new DOMWrapper(document.body)
    await flushPromises()
    await body.get('[role="combobox"]').trigger('keydown', { key: 'ArrowDown' })
    await flushPromises()
    expect(body.get('[data-value="blocked"]').attributes('data-disabled')).toBeDefined()
    await body.get('[data-value="false"]').trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(page.vm.selected).toBe('false')
    expect(new FormData(body.get('form').element as HTMLFormElement).get('active')).toBe('false')
    await chooseSelect(body.get('[role="combobox"]'), '')
    expect(page.vm.selected).toBe('')
  })

  it('禁用下拉不可展开，未选中时展示占位文案', () => {
    const page = mount(UiSelect, {
      props: { modelValue: '', disabled: true, options: [], placeholder: '请选择部门' },
      attrs: { 'aria-label': '部门' },
    })
    expect(page.get('[role="combobox"]').attributes('disabled')).toBeDefined()
    expect(page.text()).toContain('请选择部门')
  })

  it('展开后禁用会关闭选项并禁用表单值，保留原选择且不报告新的选择', async () => {
    const page = mount(UiSelect, {
      attachTo: document.body,
      props: {
        modelValue: 'active',
        name: 'status',
        options: [
          { value: 'active', label: '已启用' },
          { value: 'inactive', label: '已停用' },
        ],
      },
    })
    const body = new DOMWrapper(document.body)
    await page.get('[role="combobox"]').trigger('keydown', { key: 'ArrowDown' })
    await flushPromises()
    expect(body.find('[role="listbox"]').exists()).toBe(true)
    await page.setProps({ disabled: true })
    await flushPromises()
    expect(body.find('[role="listbox"]').exists()).toBe(false)
    expect(page.get('[role="combobox"]').attributes('disabled')).toBeDefined()
    const field = page.get<HTMLInputElement>('input[type="hidden"][name="status"]').element
    expect(field.disabled).toBe(true)
    expect(field.value).toBe('active')
    expect(page.emitted('update:modelValue')).toBeUndefined()
  })
})
