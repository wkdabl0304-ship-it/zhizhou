<!-- 会话条目：负责选择事件与当前状态语义，不直接读取或修改会话 store。 -->
<script setup lang="ts">
import { ref } from 'vue'
import { MessageSquare, Trash2 } from '@lucide/vue'
defineProps<{ title: string; active: boolean; removable?: boolean; busy?: boolean }>()
const emit = defineEmits<{ select: []; delete: [] }>()
const confirming = ref(false)
/** 确认删除后关闭本条提示，并将业务操作交给父级统一处理。 */
function confirmDelete(): void {
  confirming.value = false
  emit('delete')
}
</script>

<template>
  <div class="conversation-row">
    <button
      type="button"
      class="conversation-item"
      :class="{ 'is-active': active }"
      :aria-current="active ? 'true' : undefined"
      @click="$emit('select')"
    >
      <MessageSquare :size="15" aria-hidden="true" /><span>{{ title }}</span>
    </button>
    <button
      v-if="removable"
      type="button"
      class="conversation-delete"
      :aria-label="`删除会话：${title}`"
      :disabled="busy"
      @click="confirming = !confirming"
    >
      <Trash2 :size="14" />
    </button>
  </div>
  <div
    v-if="confirming"
    class="delete-confirmation"
    role="group"
    :aria-label="`确认删除会话：${title}`"
  >
    <span>删除这段对话？</span>
    <button type="button" :disabled="busy" @click="confirmDelete">确认删除</button>
    <button type="button" :disabled="busy" @click="confirming = false">取消</button>
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
.conversation-delete {
  display: grid;
  place-items: center;
  padding: 8px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
}
.conversation-delete:hover {
  color: var(--danger);
  background: var(--danger-soft);
}
.delete-confirmation {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px;
  font-size: 12px;
  color: var(--text-secondary);
}
.delete-confirmation button {
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--surface);
  padding: 3px 7px;
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
.conversation-item.is-active {
  background: var(--surface-active);
  color: var(--text);
}
.conversation-item.is-active svg {
  color: var(--brand);
}
</style>
