<!-- 弹窗公共底栏：统一取消、提交、等待和危险操作样式，支持外部表单及辅助说明插槽。 -->
<script setup lang="ts">
import UiButton from './UiButton.vue'
withDefaults(
  defineProps<{
    confirmLabel?: string
    cancelLabel?: string
    busy?: boolean
    disabled?: boolean
    danger?: boolean
    form?: string
    confirmType?: 'button' | 'submit'
  }>(),
  { confirmLabel: '保存', cancelLabel: '取消', confirmType: 'button' },
)
defineEmits<{ confirm: []; cancel: [] }>()
</script>
<template>
  <div class="ui-dialog-actions">
    <div v-if="$slots.default" class="ui-dialog-action-note"><slot /></div>
    <div class="ui-dialog-action-buttons">
      <UiButton data-confirm-cancel :disabled="busy" @click="$emit('cancel')">{{
        cancelLabel
      }}</UiButton>
      <UiButton
        :variant="danger ? 'danger' : 'primary'"
        :loading="busy"
        :disabled="disabled"
        :form="form"
        :type="confirmType"
        @click="$emit('confirm')"
        >{{ confirmLabel }}</UiButton
      >
    </div>
  </div>
</template>
<style scoped>
.ui-dialog-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 14px;
}
.ui-dialog-action-note {
  flex: 1;
  color: var(--text-muted);
  font-size: 11px;
}
.ui-dialog-action-buttons {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}
</style>
