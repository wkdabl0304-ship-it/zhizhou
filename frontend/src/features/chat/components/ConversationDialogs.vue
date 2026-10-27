<!-- 会话弹窗宿主：衔接改名和删除业务，公共 UI 不读取会话状态或调用接口。 -->
<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { useChatStore } from '../store'
import type { ConversationDialogRequest } from '../types'
import ConversationTitleEditor from './ConversationTitleEditor.vue'
import UiConfirmDialog from '@/shared/components/ui/UiConfirmDialog.vue'
const props = defineProps<{ request: ConversationDialogRequest; nested?: boolean }>()
const emit = defineEmits<{ close: [] }>()
const chat = useChatStore()
// 操作对象在打开时固定；切换活动会话不能把弹窗的写入目标换掉。
const row = chat.conversations.find((item) => item.id === props.request.id)
const error = ref('')
if (row) row.actionOpen = true
onBeforeUnmount(() => {
  if (row) row.actionOpen = false
})
/** 将弹窗中的标题写回原会话，错误由表单保留并显示。 */
async function rename(title: string): Promise<boolean> {
  return chat.rename(props.request.id, title)
}
/** 删除成功才关闭，冲突或网络错误留在确认弹窗，允许用户重试。 */
async function remove(): Promise<void> {
  error.value = ''
  if (await chat.remove(props.request.id)) emit('close')
  else error.value = chat.actionError || '删除未完成，请稍后重试'
}
</script>
<template>
  <ConversationTitleEditor
    v-if="row && request.kind === 'rename'"
    :title="row.title"
    :save="rename"
    :save-error="row.titleError"
    :return-focus="request.trigger"
    :layer="nested ? 1 : 0"
    @saved="emit('close')"
    @cancel="emit('close')"
  />
  <UiConfirmDialog
    v-else-if="row"
    :open="true"
    title="删除会话？"
    description="此对话将从列表移除，删除后无法在界面恢复。"
    confirm-label="确认删除"
    :busy="row.deleting"
    :error="error"
    :return-focus="request.trigger"
    :layer="nested ? 1 : 0"
    @update:open="emit('close')"
    @confirm="remove"
  >
    <blockquote class="conversation-delete-subject">{{ row.title }}</blockquote>
  </UiConfirmDialog>
</template>
<style scoped>
.conversation-delete-subject {
  margin: 0;
  padding: 12px 14px;
  border-left: 2px solid var(--border-strong);
  border-radius: 0 8px 8px 0;
  background: var(--surface-soft);
  color: var(--text);
}
</style>
