<!-- 通用复选框：原生 checkbox 保留表单与键盘语义，方框和标签组成完整点击区域。 -->
<script setup lang="ts">
import { useAttrs } from 'vue'
import { Check } from '@lucide/vue'
defineOptions({ inheritAttrs: false })
defineProps<{ disabled?: boolean }>()
const model = defineModel<boolean>({ default: false })
const attrs = useAttrs()

/** 转发原生复选框属性，外部布局类作用于整行标签。 */
function controlAttrs() {
  return Object.fromEntries(
    Object.entries(attrs).filter(([key]) => key !== 'class' && key !== 'style'),
  )
}
</script>
<template>
  <label class="ui-checkbox" :class="attrs.class" :style="attrs.style">
    <span class="ui-checkbox-box"
      ><input
        v-bind="controlAttrs()"
        v-model="model"
        class="ui-checkbox-control"
        type="checkbox"
        :disabled="disabled" /><Check :size="12" :stroke-width="2.8" aria-hidden="true"
    /></span>
    <span v-if="$slots.default || $slots.description" class="ui-checkbox-copy"
      ><span v-if="$slots.default"><slot /></span
      ><small v-if="$slots.description"><slot name="description" /></small
    ></span>
  </label>
</template>
