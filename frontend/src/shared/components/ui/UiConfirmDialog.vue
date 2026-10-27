<!-- 公共确认弹窗：复用模态和底栏，业务调用方控制请求、错误及成功后的关闭时机。 -->
<script setup lang="ts">
import UiModal from './UiModal.vue'
import UiDialogActions from './UiDialogActions.vue'
withDefaults(
  defineProps<{
    open: boolean
    title: string
    description?: string
    confirmLabel?: string
    cancelLabel?: string
    danger?: boolean
    busy?: boolean
    error?: string
    returnFocus?: HTMLElement | null
    layer?: number
  }>(),
  { confirmLabel: '确认', cancelLabel: '取消', danger: true },
)
defineEmits<{ 'update:open': [value: boolean]; confirm: [] }>()
</script>
<template>
  <UiModal
    :open="open"
    :title="title"
    :description="description"
    size="sm"
    :busy="busy"
    :return-focus="returnFocus"
    :layer="layer"
    initial-focus="[data-confirm-cancel]"
    @update:open="$emit('update:open', $event)"
  >
    <div v-if="$slots.default" class="ui-confirm-content"><slot /></div>
    <p v-if="error" class="ui-confirm-error" role="alert">{{ error }}</p>
    <template #footer>
      <UiDialogActions
        :confirm-label="confirmLabel"
        :cancel-label="cancelLabel"
        :danger="danger"
        :busy="busy"
        @cancel="$emit('update:open', false)"
        @confirm="$emit('confirm')"
      />
    </template>
  </UiModal>
</template>
<style scoped>
.ui-confirm-content {
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.7;
  overflow-wrap: anywhere;
}
.ui-confirm-error {
  color: var(--danger);
  font-size: 12px;
  margin: 12px 0 0;
}
</style>
