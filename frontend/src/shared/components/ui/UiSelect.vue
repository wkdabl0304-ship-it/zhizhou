<!-- 通用单选下拉：以 Reka 提供键盘、焦点和触屏交互，统一弹出菜单、空值与表单提交语义。 -->
<script setup lang="ts">
import { computed, inject, useAttrs, watch, ref } from 'vue'
import { Check, ChevronDown, ChevronUp } from '@lucide/vue'
import {
  SelectRoot,
  SelectTrigger,
  SelectValue,
  SelectPortal,
  SelectContent,
  SelectViewport,
  SelectItem,
  SelectItemText,
  SelectItemIndicator,
  SelectScrollUpButton,
  SelectScrollDownButton,
} from 'reka-ui'
import type { UiSelectOption } from './controls'

defineOptions({ inheritAttrs: false })
const props = withDefaults(
  defineProps<{
    options: UiSelectOption[]
    placeholder?: string
    disabled?: boolean
    name?: string
    size?: 'sm' | 'md'
  }>(),
  { placeholder: '请选择', size: 'md' },
)
const model = defineModel<string>({ default: '' })
const attrs = useAttrs(),
  open = ref(false)
const depth = inject<number>('zhizhou:modal-depth', 0)
// Reka 不接受空字符串选项；给所有内部值加同一前缀，避免“全部”与合法业务值冲突。
const internal = computed(() =>
  props.options.some((option) => option.value === model.value) ? `value:${model.value}` : '',
)

/** 将选中项还原为调用方原值；只接受当前目录中存在且可选的值。 */
function update(value: unknown): void {
  if (typeof value !== 'string' || !value.startsWith('value:')) return
  const selected = value.slice(6)
  if (props.options.some((option) => option.value === selected && !option.disabled))
    model.value = selected
}
// 禁用时关闭已经展开的菜单，避免继续选择过时选项。
watch(
  () => props.disabled,
  (disabled) => {
    if (disabled) open.value = false
  },
)
</script>
<template>
  <!-- 使用原业务值提交表单；Reka 的内部代理值不写入表单或业务请求。 -->
  <input v-if="name" type="hidden" :name="name" :value="model" :disabled="disabled" />
  <SelectRoot
    :model-value="internal"
    v-model:open="open"
    :disabled="disabled"
    @update:model-value="update"
  >
    <SelectTrigger
      v-bind="$attrs"
      class="ui-select-trigger"
      :class="`ui-control--${size}`"
      :data-field="name"
      :data-invalid="
        attrs['aria-invalid'] === true || attrs['aria-invalid'] === 'true' || undefined
      "
      ><SelectValue :placeholder="placeholder" /><ChevronDown
        class="ui-select-chevron"
        :size="15"
        aria-hidden="true"
    /></SelectTrigger>
    <SelectPortal
      ><SelectContent
        class="ui-select-content"
        :style="{ zIndex: `calc(var(--z-menu) + ${depth * 2})` }"
        position="popper"
        :side-offset="6"
        :collision-padding="12"
        :body-lock="false"
        :aria-label="attrs['aria-label'] ? `${attrs['aria-label']}选项` : '可选项'"
      >
        <SelectScrollUpButton class="ui-select-scroll"
          ><ChevronUp :size="15"
        /></SelectScrollUpButton>
        <SelectViewport class="ui-select-viewport"
          ><SelectItem
            v-for="option in options"
            :key="option.value"
            class="ui-select-option"
            :value="`value:${option.value}`"
            :disabled="option.disabled"
            :data-value="option.value"
            ><SelectItemText>{{ option.label }}</SelectItemText
            ><SelectItemIndicator class="ui-select-indicator"
              ><Check :size="15" /></SelectItemIndicator
          ></SelectItem>
          <p v-if="!options.length" class="ui-select-empty">暂无可选项</p></SelectViewport
        >
        <SelectScrollDownButton class="ui-select-scroll"
          ><ChevronDown :size="15"
        /></SelectScrollDownButton> </SelectContent
    ></SelectPortal>
  </SelectRoot>
</template>
