<!-- 上传策略编辑：用数字与可选容量单位表达上限，精确转换后提交版本化策略。 -->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ApiError } from '@/features/auth/authenticated'
import UiModal from '@/shared/components/ui/UiModal.vue'
import UiDialogActions from '@/shared/components/ui/UiDialogActions.vue'
import UiInput from '@/shared/components/ui/UiInput.vue'
import UiSelect from '@/shared/components/ui/UiSelect.vue'
import UiFeedback from '@/shared/components/ui/UiFeedback.vue'
import UiButton from '@/shared/components/ui/UiButton.vue'
import { uploadLimit } from '../api'
import { fileError } from '../format'
import { editUploadSize, parseUploadSize, SIZE_UNIT_OPTIONS } from '../upload-size'
import type { FileSpace, UploadLimit } from '../types'

const props = defineProps<{ space: FileSpace }>()
const emit = defineEmits<{ close: []; saved: []; conflict: [] }>()
const policy = ref<UploadLimit | null>(null),
  input = ref(''),
  error = ref('')
const loading = ref(false),
  saving = ref(false),
  attempted = ref(false),
  stale = ref(false)
const controller = new AbortController()
const unit = ref('MB')
const initialDraft = ref<{ value: string; unit: string } | null>(null)
// 界面显示友好小数，但直接保存保留原始精确策略，避免显示精度改变历史上限。
const bytes = computed(() => {
  const parsed = parseUploadSize(input.value, unit.value)
  if (parsed === null) return null
  if (
    policy.value &&
    initialDraft.value?.unit === unit.value &&
    Number(initialDraft.value.value) === Number(input.value)
  )
    return policy.value.max_file_size_bytes
  return parsed
})
const validation = computed(() =>
  bytes.value === null ? '请输入大于 0 且在 1 B～1 TB 范围内的容量，支持小数。' : '',
)
const description = computed(() =>
  props.space.kind === 'personal'
    ? '适用于所有用户的个人空间，仅影响新上传文件。'
    : `适用于${props.space.name}，仅影响新上传文件。`,
)

/** 获取最新策略版本，读取失败只提供显式重试入口。 */
async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const result = await uploadLimit(props.space, controller.signal)
    if (controller.signal.aborted) return
    policy.value = result
    const draft = editUploadSize(result.max_file_size_bytes)
    initialDraft.value = draft
    input.value = draft.value
    unit.value = draft.unit
  } catch (failure) {
    if (!controller.signal.aborted) error.value = fileError(failure)
  } finally {
    loading.value = false
  }
}

/** 提交带版本的策略，冲突后要求重新打开，避免覆盖另一管理者的更新。 */
async function save(): Promise<void> {
  if (saving.value || !policy.value || stale.value) return
  attempted.value = true
  if (validation.value || bytes.value === null) return
  saving.value = true
  error.value = ''
  try {
    await uploadLimit(props.space, controller.signal, {
      max_file_size_bytes: bytes.value,
      version: policy.value.version,
    })
    if (!controller.signal.aborted) emit('saved')
  } catch (failure) {
    if (controller.signal.aborted) return
    error.value = fileError(failure)
    if (failure instanceof ApiError && [403, 404, 409].includes(failure.status)) {
      stale.value = true
      emit('conflict')
    }
  } finally {
    saving.value = false
  }
}

onMounted(load)
onBeforeUnmount(() => controller.abort())
</script>
<template>
  <UiModal
    :open="true"
    title="单文件上传上限"
    :description="description"
    size="md"
    :busy="saving"
    @update:open="emit('close')"
  >
    <p v-if="loading" role="status">正在读取上传策略…</p>
    <form v-if="policy" id="upload-limit" class="file-form" @submit.prevent="save">
      <div class="file-size-fields">
        <label for="upload-limit-amount"
          >单文件大小
          <UiInput
            id="upload-limit-amount"
            v-model="input"
            inputmode="decimal"
            :disabled="saving || stale"
            :aria-invalid="!!error || (attempted && !!validation)"
            :aria-describedby="
              error || (attempted && validation)
                ? 'upload-limit-help upload-limit-error'
                : 'upload-limit-help'
            "
            @input="error = ''"
          />
        </label>
        <label for="upload-limit-unit"
          >容量单位
          <UiSelect
            id="upload-limit-unit"
            v-model="unit"
            :options="SIZE_UNIT_OPTIONS"
            aria-label="容量单位"
            :disabled="saving || stale"
            @update:model-value="error = ''"
          />
        </label>
      </div>
      <p id="upload-limit-help" class="file-hint">支持小数，最大 1 TB（1 KB = 1024 B）。</p>
    </form>
    <UiFeedback
      v-if="error || (attempted && validation)"
      id="upload-limit-error"
      :message="error || validation"
    />
    <UiButton v-if="!policy && !loading" @click="load">重新读取策略</UiButton>
    <template #footer
      ><UiDialogActions
        form="upload-limit"
        confirm-type="submit"
        confirm-label="保存上限"
        :busy="saving"
        :disabled="!policy || loading || stale"
        @cancel="emit('close')"
    /></template>
  </UiModal>
</template>
