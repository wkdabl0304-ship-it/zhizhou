<!-- 文件操作表单：冻结目标与版本，复用公共弹层；冲突同步目录，保留原草稿且不重放请求。 -->
<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { ApiError } from '@/features/auth/authenticated'
import UiModal from '@/shared/components/ui/UiModal.vue'
import UiDialogActions from '@/shared/components/ui/UiDialogActions.vue'
import UiInput from '@/shared/components/ui/UiInput.vue'
import UiFeedback from '@/shared/components/ui/UiFeedback.vue'
import { createFolder, deleteEntry, renameEntry } from '../api'
import { fileError, validateName } from '../format'
import type { FileAction } from '../types'

const props = defineProps<{ action: FileAction }>()
const emit = defineEmits<{ close: []; saved: []; conflict: [] }>()
const input = ref(props.action.kind === 'rename' ? props.action.entry.name : '')
const busy = ref(false),
  error = ref(''),
  attempted = ref(false),
  stale = ref(false)
const controller = new AbortController()
const composing = ref(false)
const title = computed(
  () => ({ create: '新建文件夹', rename: '重命名', delete: '删除资料' })[props.action.kind],
)
const description = computed(() =>
  props.action.kind === 'delete'
    ? 'entry' in props.action && props.action.entry.kind === 'folder'
      ? '文件夹及其所有下级资料将一并删除，无法恢复。'
      : '原文件将被删除，无法恢复。'
    : '同一目录的文件与文件夹名称不能重复。',
)
const validation = computed(() => (props.action.kind === 'delete' ? '' : validateName(input.value)))

/** 提交用户确认的单次变更，版本失效后必须关闭并重新选择目标。 */
async function save(): Promise<void> {
  if (busy.value || stale.value || composing.value) return
  attempted.value = true
  if (validation.value) return
  busy.value = true
  error.value = ''
  try {
    const action = props.action
    if (action.kind === 'create')
      await createFolder(
        action.space.id,
        action.parentId,
        input.value.trim().normalize('NFC'),
        controller.signal,
      )
    else if (action.kind === 'rename')
      await renameEntry(action.entry, input.value.trim().normalize('NFC'), controller.signal)
    else await deleteEntry(action.entry, controller.signal)
    if (!controller.signal.aborted) emit('saved')
  } catch (failure) {
    if (controller.signal.aborted) return
    error.value = fileError(failure)
    if (failure instanceof ApiError && [403, 404, 409].includes(failure.status)) {
      stale.value = failure.code !== 40909
      emit('conflict')
    }
  } finally {
    busy.value = false
  }
}

/** 保留中文输入法的候选确认，避免 Enter 在组词时提前提交名称。 */
function guardEnter(event: KeyboardEvent): void {
  if (event.isComposing || composing.value) event.preventDefault()
}

// 离页终止请求；即便写入已由后端完成，也不向已卸载页面发出通知。
onBeforeUnmount(() => controller.abort())
</script>
<template>
  <UiModal
    :open="true"
    :title="title"
    :description="description"
    :busy="busy"
    size="md"
    :initial-focus="action.kind === 'delete' ? '[data-confirm-cancel]' : '#file-name'"
    @update:open="emit('close')"
  >
    <form
      id="file-action"
      class="file-form"
      @submit.prevent="save"
      @keydown.enter="guardEnter"
      @compositionstart="composing = true"
      @compositionend="composing = false"
    >
      <p v-if="'entry' in action" class="file-target">{{ action.entry.name }}</p>
      <label v-if="action.kind !== 'delete'" for="file-name"
        >名称
        <UiInput
          id="file-name"
          v-model="input"
          autocomplete="off"
          :disabled="busy || stale"
          :aria-invalid="!!error || (attempted && !!validation)"
          :aria-describedby="error || (attempted && validation) ? 'file-action-error' : undefined"
          @input="error = ''"
        />
      </label>
      <UiFeedback
        v-if="error || (attempted && validation)"
        id="file-action-error"
        :message="error || validation"
      />
    </form>
    <template #footer
      ><UiDialogActions
        form="file-action"
        confirm-type="submit"
        :busy="busy"
        :disabled="stale"
        :danger="action.kind === 'delete'"
        :confirm-label="
          action.kind === 'delete'
            ? '确认删除'
            : action.kind === 'create'
              ? '创建文件夹'
              : '保存名称'
        "
        @cancel="emit('close')"
    /></template>
  </UiModal>
</template>
