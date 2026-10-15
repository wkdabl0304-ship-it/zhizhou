<!-- 会话条目：负责选择事件与当前状态语义，不直接读取或修改会话 store。 -->
<script setup lang="ts">
import { MessageSquare } from '@lucide/vue'
defineProps<{ title: string; active: boolean }>()
defineEmits<{ select: [] }>()
</script>

<template>
  <button
    type="button"
    class="conversation-item"
    :class="{ 'is-active': active }"
    :aria-current="active ? 'true' : undefined"
    @click="$emit('select')"
  >
    <MessageSquare :size="15" aria-hidden="true" /><span>{{ title }}</span>
  </button>
</template>

<style scoped>
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
