<!-- 会话条目：报告选择、双击改名及按钮操作，业务弹窗统一由工作区宿主管理。 -->
<script setup lang="ts">
import { MessageSquare, Pencil, Trash2 } from '@lucide/vue'
import { onBeforeUnmount, ref } from 'vue'
const props = defineProps<{
  title: string
  active: boolean
  removable?: boolean
  busy?: boolean
  renamable?: boolean
  renameDisabled?: boolean
}>()
const emit = defineEmits<{
  select: []
  rename: [trigger: HTMLElement]
  delete: [trigger: HTMLElement]
}>()
let selectionTimer: ReturnType<typeof setTimeout> | undefined
const selecting = ref(false)
/** 释放尚未确认的单击，避免双击改名时又触发导航、关闭抽屉或清空消息草稿。 */
function cancelSelection(): void {
  clearTimeout(selectionTimer)
  selectionTimer = undefined
  selecting.value = false
}
/** 鼠标单击等待短暂双击窗口，键盘选择立即执行。 */
function select(event: MouseEvent): void {
  cancelSelection()
  if (!props.renamable || event.detail === 0) emit('select')
  else if (event.detail === 1) {
    selecting.value = true
    selectionTimer = setTimeout(() => {
      selecting.value = false
      emit('select')
    }, 300)
  }
}
onBeforeUnmount(cancelSelection)
/** 从铅笔按钮或双击标题进入同一改名流程，保留真实触发元素以恢复焦点。 */
function rename(event: MouseEvent): void {
  cancelSelection()
  if (props.renamable && !props.renameDisabled) emit('rename', event.currentTarget as HTMLElement)
}
</script>
<template>
  <div class="conversation-row">
    <button
      type="button"
      class="conversation-item"
      :class="{ 'is-active': active }"
      :aria-current="active ? 'true' : undefined"
      :aria-busy="selecting || undefined"
      @click="select"
      @dblclick.stop="rename"
    >
      <MessageSquare :size="15" aria-hidden="true" /><span>{{ title }}</span>
    </button>
    <button
      v-if="renamable"
      type="button"
      class="conversation-rename"
      :aria-label="`修改会话标题：${title}`"
      :disabled="renameDisabled"
      @click="rename"
    >
      <Pencil :size="13" aria-hidden="true" />
    </button>
    <button
      v-if="removable"
      type="button"
      class="conversation-delete"
      :aria-label="`删除会话：${title}`"
      :disabled="busy"
      @click="emit('delete', $event.currentTarget as HTMLElement)"
    >
      <Trash2 :size="14" aria-hidden="true" />
    </button>
  </div>
</template>

<style scoped>
.conversation-row {
  display: flex;
  align-items: center;
  min-width: 0;
}
.conversation-row .conversation-item {
  flex: 1;
  min-width: 0;
}
.conversation-delete,
.conversation-rename {
  display: grid;
  place-items: center;
  padding: 8px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
}
.conversation-rename:hover {
  color: var(--brand);
  background: var(--surface-hover);
}
.conversation-rename:focus-visible,
.conversation-delete:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: -2px;
}
.conversation-rename:disabled {
  opacity: 0.5;
  cursor: default;
}
.conversation-delete:hover {
  color: var(--danger);
  background: var(--danger-soft);
}
.conversation-item {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  min-height: 38px;
  padding: 9px 10px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  text-align: left;
  font-size: 12px;
}
.conversation-item span {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.conversation-item svg {
  color: var(--text-muted);
}
.conversation-item:hover {
  background: var(--surface-hover);
}
.conversation-item[aria-busy='true'] {
  background: var(--surface-hover);
}
.conversation-item.is-active {
  background: var(--surface-active);
  color: var(--text);
}
.conversation-item.is-active svg {
  color: var(--brand);
}
</style>
