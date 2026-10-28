<!-- 配置编辑器外壳：统一提交、冲突提示、未保存关闭确认和离页保护，表单字段由业务插槽提供。 -->
<script setup lang="ts">
import { onBeforeUnmount, ref, watchEffect, useId } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { useAuthStore } from '@/features/auth/store'
import UiModal from '@/shared/components/ui/UiModal.vue'
import UiConfirmDialog from '@/shared/components/ui/UiConfirmDialog.vue'
import UiDialogActions from '@/shared/components/ui/UiDialogActions.vue'
const props = defineProps<{
  title: string
  dirty: boolean
  busy: boolean
  loading?: boolean
  error: string
  conflict: boolean
  description?: string
  returnFocus?: HTMLElement | null
}>()
const emit = defineEmits<{
  submit: []
  close: []
  state: [value: { dirty: boolean; busy: boolean }]
}>()
// 父级供应商面板据此保护保存过程，未保存草稿仍只由当前编辑弹窗持有。
watchEffect(() => emit('state', { dirty: props.dirty, busy: props.busy }))
const discarding = ref(false)
// 每个编辑器分配独立表单标识，公共底栏可跨内容区域提交正确的表单。
const formId = useId()
let leaving: ((allowed: boolean) => void) | undefined
const auth = useAuthStore()
/** 关闭时保留正在保存的表单；有修改时先展示明确的放弃确认。 */
function close(): void {
  if (props.busy) return
  if (props.dirty) discarding.value = true
  else emit('close')
}
/** 确认放弃当前草稿，按调用来源关闭编辑器或继续路由导航。 */
function discard(): void {
  discarding.value = false
  if (leaving) {
    leaving(true)
    leaving = undefined
  } else emit('close')
}
/** 取消离页或关闭操作，继续保留当前填写内容。 */
function keep(): void {
  discarding.value = false
  leaving?.(false)
  leaving = undefined
}
// 用户主动离开时询问草稿；认证失效或失去管理权限必须允许根组件导航并清理秘密输入。
onBeforeRouteLeave(() => {
  if (!auth.isAuthenticated || !auth.can('model:manage')) return true
  if (props.busy) return false
  if (!props.dirty) return true
  discarding.value = true
  return new Promise<boolean>((resolve) => {
    leaving = resolve
  })
})
onBeforeUnmount(() => {
  leaving?.(false)
})
</script>
<template>
  <UiModal
    :open="true"
    :title="title"
    :description="description ?? '保存配置后，可单独测试或设为全局默认。'"
    size="lg"
    layout="panel"
    :return-focus="returnFocus"
    :close-disabled="busy"
    @update:open="close"
  >
    <form :id="formId" class="config-fields" novalidate @submit.prevent="emit('submit')">
      <fieldset :disabled="busy || loading"><slot /></fieldset>
      <p v-if="error" class="config-error" role="alert">{{ error }}</p>
      <p v-if="conflict" class="config-hint">当前输入仍保留。关闭后重新编辑，可使用最新配置。</p>
    </form>
    <template #footer
      ><UiDialogActions
        :form="formId"
        confirm-type="submit"
        confirm-label="保存配置"
        :busy="busy"
        :disabled="loading"
        @cancel="close"
        ><small>修改从下一轮聊天生效</small></UiDialogActions
      ></template
    >
    <UiConfirmDialog
      v-if="discarding"
      :open="true"
      title="放弃未保存的更改？"
      description="本次填写的内容不会保存。"
      confirm-label="放弃更改"
      cancel-label="继续编辑"
      @update:open="keep"
      @confirm="discard"
    />
  </UiModal>
</template>
