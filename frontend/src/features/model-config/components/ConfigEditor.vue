<!-- 配置编辑器外壳：统一提交、冲突提示、未保存关闭确认和离页保护，表单字段由业务插槽提供。 -->
<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { useAuthStore } from '@/features/auth/store'
import UiModal from '@/shared/components/ui/UiModal.vue'
import UiButton from '@/shared/components/ui/UiButton.vue'
const props = defineProps<{
  title: string
  dirty: boolean
  busy: boolean
  loading?: boolean
  error: string
  conflict: boolean
}>()
const emit = defineEmits<{ submit: []; close: []; reload: [] }>()
const discarding = ref(false)
let leaving: ((allowed: boolean) => void) | undefined
const auth = useAuthStore()
/** 关闭时保留正在保存的表单；有修改时先展示明确的放弃确认。 */
function close(): void {
  if (props.busy) return
  if (props.dirty) discarding.value = true
  else emit('close')
}
/** 确认放弃当前草稿，按调用来源关闭抽屉或继续路由导航。 */
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
// 用户主动离开时询问草稿；认证失效必须允许根组件导航并清理秘密输入。
onBeforeRouteLeave(() => {
  if (!auth.isAuthenticated || !props.dirty) return true
  if (props.busy) return false
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
    description="保存配置后，可单独测试或设为全局默认。"
    drawer
    @update:open="close"
  >
    <form
      id="model-config-editor"
      class="config-fields"
      novalidate
      @submit.prevent="emit('submit')"
    >
      <fieldset :disabled="busy || loading"><slot /></fieldset>
      <p v-if="error" class="config-error" role="alert">{{ error }}</p>
      <UiButton v-if="conflict" size="sm" :disabled="busy" @click="emit('reload')"
        >读取最新版本，重新编辑</UiButton
      >
    </form>
    <footer class="config-editor-footer">
      <small>修改从下一轮聊天生效</small>
      <div class="config-actions">
        <UiButton size="sm" :disabled="busy" @click="close">取消</UiButton
        ><UiButton
          form="model-config-editor"
          type="submit"
          variant="primary"
          size="sm"
          :loading="busy"
          :disabled="loading"
          >保存配置</UiButton
        >
      </div>
    </footer>
    <UiModal
      v-if="discarding"
      :open="true"
      title="放弃未保存的更改？"
      description="本次填写的内容不会保存。"
      @update:open="keep"
    >
      <div class="config-actions config-confirm-actions">
        <UiButton @click="keep">继续编辑</UiButton
        ><UiButton class="config-danger" @click="discard">放弃更改</UiButton>
      </div>
    </UiModal>
  </UiModal>
</template>
