<!-- 通用单行输入框：统一输入外观、前后缀与状态，原生输入保留表单、自动填充和输入法语义。 -->
<script setup lang="ts">
import { ref, useAttrs } from 'vue'

defineOptions({ inheritAttrs: false })
const props = withDefaults(defineProps<{ size?: 'sm' | 'md'; disabled?: boolean }>(), {
  size: 'md',
})
const model = defineModel<string | number>()
const attrs = useAttrs()
const element = ref<HTMLInputElement>()
let composing = false

/** 将原生输入属性和监听传给实际输入，布局类和样式留给控件外壳。 */
function controlAttrs() {
  return Object.fromEntries(
    Object.entries(attrs).filter(([key]) => key !== 'class' && key !== 'style'),
  )
}

/** 同步原始输入内容；数字转换由调用方的 v-model.number 决定，密码和空格保持原样。 */
function update(event: Event): void {
  if (composing) return
  model.value = (event.target as HTMLInputElement).value
}

/** 保留输入法候选阶段，直到组成结束才提交新的模型值。 */
function startComposition(): void {
  composing = true
}

/** 在中文等输入法确认后同步完整内容。 */
function finishComposition(event: Event): void {
  composing = false
  update(event)
}

/** 聚焦实际输入节点，供弹窗和业务表单恢复键盘位置。 */
function focus(): void {
  element.value?.focus()
}

/** 选中已有内容，供会话标题等编辑入口直接替换。 */
function select(): void {
  element.value?.select()
}
defineExpose({ focus, select, element })
</script>
<template>
  <span
    class="ui-input"
    :class="[attrs.class, `ui-control--${props.size}`]"
    :style="attrs.style"
    :data-invalid="attrs['aria-invalid'] === true || attrs['aria-invalid'] === 'true' || undefined"
  >
    <span v-if="$slots.prefix" class="ui-input-prefix"><slot name="prefix" /></span>
    <input
      ref="element"
      v-bind="controlAttrs()"
      class="ui-input-control"
      :value="'value' in attrs ? attrs.value : (model ?? '')"
      :disabled="disabled"
      @input="update"
      @compositionstart="startComposition"
      @compositionend="finishComposition"
    />
    <span v-if="$slots.suffix" class="ui-input-suffix"><slot name="suffix" /></span>
  </span>
</template>
