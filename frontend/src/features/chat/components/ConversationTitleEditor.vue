<!-- 会话标题弹窗：负责草稿、Unicode 长度校验和提交反馈，保存由工作区状态层提供。 -->
<script setup lang="ts">
import UiInput from '@/shared/components/ui/UiInput.vue'
import { computed, nextTick, ref, useId } from 'vue'
import UiModal from '@/shared/components/ui/UiModal.vue'
import UiDialogActions from '@/shared/components/ui/UiDialogActions.vue'
import { normalizeTitle, titleIssue, TITLE_LIMIT } from '../titles'

const props = defineProps<{
  title: string
  returnFocus?: HTMLElement | null
  layer?: number
  save: (title: string) => Promise<boolean>
  saveError?: string
}>()
const emit = defineEmits<{ saved: []; cancel: [] }>()
// 只在进入编辑时取初始值；自动标题或目录更新不能替换正在输入的草稿。
const draft = ref(props.title),
  error = ref(''),
  saving = ref(false)
const input = ref<InstanceType<typeof UiInput>>()
const formId = useId()
const length = computed(() => Array.from(normalizeTitle(draft.value)).length)

/** 校验并保存标题，失败保留输入；同名保存仍发请求，以将自动标题改为手动标题。 */
async function submit(): Promise<void> {
  if (saving.value) return
  error.value = titleIssue(draft.value)
  if (error.value) return
  saving.value = true
  try {
    if (await props.save(normalizeTitle(draft.value))) emit('saved')
    else {
      await nextTick()
      error.value = props.saveError || '标题未保存，请稍后重试'
    }
  } catch {
    error.value = '标题未保存，请稍后重试'
  } finally {
    saving.value = false
  }
}
/** 取消尚未提交的标题编辑，保存期间等待服务端结果，避免将已写入误认为已取消。 */
function cancel(): void {
  if (!saving.value) emit('cancel')
}
/** 处理编辑快捷键，中文输入法确认不提交，Esc 不穿透到移动导航抽屉。 */
function keydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') event.stopPropagation()
  if (event.isComposing || event.keyCode === 229) {
    if (event.key === 'Enter') event.preventDefault()
    return
  }
  if (event.key === 'Escape') {
    event.preventDefault()
    cancel()
  }
}
/** 在公共弹窗打开后选中原标题，覆盖默认的关闭按钮焦点。 */
function selectTitle(event: Event): void {
  event.preventDefault()
  input.value?.focus()
  input.value?.select()
}
</script>

<template>
  <UiModal
    :open="true"
    title="修改会话标题"
    description="给这段对话一个清晰的名字。"
    size="md"
    :busy="saving"
    :return-focus="returnFocus"
    :layer="layer"
    :close-on-outside="false"
    @update:open="cancel"
    @open-auto-focus="selectTitle"
  >
    <form
      :id="formId"
      class="conversation-title-editor"
      aria-label="修改会话标题"
      :aria-busy="saving"
      novalidate
      @submit.prevent="submit"
      @keydown="keydown"
    >
      <label :for="formId + '-input'">会话标题</label>
      <UiInput
        :id="formId + '-input'"
        ref="input"
        v-model="draft"
        name="conversation_title"
        aria-label="会话标题"
        :disabled="saving"
        :aria-invalid="!!error"
        :aria-describedby="formId + '-hint'"
        autocomplete="off"
        @input="error = ''"
      />
      <div :id="formId + '-hint'" class="title-editor-hint">
        <span>最多 {{ TITLE_LIMIT }} 个字符</span
        ><span :class="{ 'is-invalid': length > TITLE_LIMIT }">{{ length }}/{{ TITLE_LIMIT }}</span>
      </div>
      <p v-if="error" role="alert">{{ error }}</p>
    </form>
    <template #footer
      ><UiDialogActions
        confirm-label="保存标题"
        cancel-label="取消修改标题"
        :busy="saving"
        :form="formId"
        confirm-type="submit"
        @cancel="cancel"
    /></template>
  </UiModal>
</template>
<style scoped>
.conversation-title-editor label {
  display: block;
  margin-bottom: 10px;
  color: var(--text-secondary);
  font-size: 12px;
}
.title-editor-hint {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-top: 10px;
  color: var(--text-muted);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.conversation-title-editor p,
.is-invalid {
  color: var(--danger);
}
.conversation-title-editor p {
  margin: 14px 0 0;
  font-size: 12px;
  line-height: 1.6;
}
</style>
