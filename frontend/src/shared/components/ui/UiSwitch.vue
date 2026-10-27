<!-- 通用受控开关：状态由调用方保存成功后更新，支持 Reka 的键盘与无障碍语义。 -->
<script setup lang="ts">
import { SwitchRoot, SwitchThumb } from 'reka-ui'
defineProps<{ modelValue: boolean; label: string; disabled?: boolean; busy?: boolean }>()
defineEmits<{ 'update:modelValue': [value: boolean] }>()
</script>
<template>
  <SwitchRoot
    class="ui-switch"
    :model-value="modelValue"
    :aria-label="label"
    :aria-busy="busy || undefined"
    :disabled="disabled || busy"
    @update:model-value="$emit('update:modelValue', $event)"
    ><SwitchThumb class="ui-switch-thumb"
  /></SwitchRoot>
</template>
<style scoped>
.ui-switch {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  width: 42px;
  height: 24px;
  padding: 3px;
  border: 1px solid var(--border-strong);
  border-radius: 99px;
  background: var(--surface-hover);
  cursor: pointer;
  transition: background var(--duration-fast);
}
.ui-switch[data-state='checked'] {
  background: var(--brand);
  border-color: var(--brand);
}
.ui-switch-thumb {
  display: block;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--surface);
  box-shadow: 0 1px 3px rgb(0 0 0 / 15%);
  transition: transform var(--duration-fast);
}
.ui-switch[data-state='checked'] .ui-switch-thumb {
  transform: translateX(18px);
  background: var(--brand-contrast);
}
.ui-switch:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: 3px;
}
.ui-switch:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
@media (prefers-reduced-motion: reduce) {
  .ui-switch,
  .ui-switch-thumb {
    transition: none;
  }
}
</style>
