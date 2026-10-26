<!-- 聊天默认模型状态：首次加载、窗口重新激活时刷新共享引用；无可用模型仅阻止发送，不禁用草稿。 -->
<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import { useModelConfigStore } from '../store'
const store = useModelConfigStore()
/** 页面可见时重新读取全局默认，捕获其他用户或标签页的修改。 */
function refresh(): void {
  if (!document.hidden) void store.loadDefault()
}
onMounted(() => {
  if (!store.selected) refresh()
  window.addEventListener('focus', refresh)
  document.addEventListener('visibilitychange', refresh)
})
onBeforeUnmount(() => {
  window.removeEventListener('focus', refresh)
  document.removeEventListener('visibilitychange', refresh)
})
</script>
<template>
  <section class="chat-model-status" aria-label="聊天模型状态">
    <template v-if="store.defaultError"
      ><p role="alert">{{ store.defaultError }}</p>
      <button type="button" :disabled="store.defaultLoading" @click="store.loadDefault">
        重试读取默认模型
      </button></template
    >
    <p v-else-if="store.defaultLoading && !store.selected" role="status">正在读取默认模型…</p>
    <template v-else-if="!store.ready"
      ><p>
        {{
          store.selected?.model
            ? '默认模型暂不可用，请选择可用方案。'
            : '尚未配置默认模型，你可以先写草稿，配置完成后再发送。'
        }}
      </p>
      <RouterLink to="/models">前往模型管理</RouterLink></template
    >
    <RouterLink v-else to="/models">全局默认 · {{ store.selected?.model?.name }}</RouterLink>
  </section>
</template>
<style scoped>
.chat-model-status {
  z-index: 1;
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
  padding: 7px 20px;
  color: var(--text-secondary);
  font-size: 12px;
}
.chat-model-status p {
  margin: 0;
}
.chat-model-status a {
  color: var(--brand);
  text-decoration: none;
}
.chat-model-status button {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--brand);
  padding: 4px 8px;
}
</style>
