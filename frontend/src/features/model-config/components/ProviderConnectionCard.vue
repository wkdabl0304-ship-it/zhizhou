<!-- 供应商连接卡片：展示连接摘要与独立开关，通过事件交给弹窗处理切换、草稿和写入。 -->
<script setup lang="ts">
import { Pencil, Trash2 } from '@lucide/vue'
import UiButton from '@/shared/components/ui/UiButton.vue'
import UiSwitch from '@/shared/components/ui/UiSwitch.vue'
import { formatLabels } from '../validation'
import type { ProviderConfiguration } from '../types'

defineProps<{
  connection: ProviderConfiguration
  selected: boolean
  busy: boolean
  blocked: boolean
}>()
defineEmits<{ select: []; toggle: []; edit: []; delete: [] }>()
</script>

<template>
  <article
    class="provider-connection-card"
    :class="{ 'is-selected': selected }"
    :aria-label="`供应商连接：${connection.name}`"
  >
    <div class="connection-card-heading">
      <button
        type="button"
        class="connection-card-select"
        :aria-label="`切换连接 ${connection.name}`"
        :aria-pressed="selected"
        :disabled="busy"
        @click="$emit('select')"
      >
        <span class="connection-card-selection">{{ selected ? '当前连接' : '查看模型 →' }}</span>
        <strong>{{ connection.name }}</strong>
      </button>
      <UiSwitch
        :model-value="connection.enabled"
        :label="`启用供应商连接 ${connection.name}`"
        :disabled="busy || blocked"
        :busy="busy"
        @update:model-value="$emit('toggle')"
      />
    </div>
    <p class="connection-card-meta">{{ formatLabels[connection.api_format] }}</p>
    <code v-if="connection.endpoint_config.base_url" class="config-endpoint-url">{{
      connection.endpoint_config.base_url
    }}</code>
    <div class="connection-card-footer">
      <span class="connection-card-key"
        >{{ connection.api_key_configured ? '密钥已配置' : '密钥未配置' }} ·
        {{ connection.enabled ? '已启用' : '已停用' }}</span
      >
      <div class="config-actions">
        <UiButton
          size="sm"
          variant="ghost"
          aria-label="编辑供应商"
          :disabled="busy || blocked"
          @click="$emit('edit')"
          ><Pencil :size="13" aria-hidden="true" />编辑</UiButton
        >
        <UiButton
          size="sm"
          variant="ghost"
          class="config-danger"
          aria-label="删除供应商"
          :disabled="busy || blocked"
          @click="$emit('delete')"
          ><Trash2 :size="13" aria-hidden="true" />删除</UiButton
        >
      </div>
    </div>
    <slot />
  </article>
</template>

<style scoped>
.provider-connection-card {
  min-width: 0;
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface);
}
.provider-connection-card.is-selected {
  border-color: var(--brand);
  box-shadow: inset 3px 0 0 var(--brand);
}
.connection-card-heading {
  display: flex;
  align-items: center;
  gap: 12px;
}
.connection-card-select {
  flex: 1;
  min-width: 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text);
  text-align: left;
  cursor: pointer;
}
.connection-card-select:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: 4px;
  border-radius: 3px;
}
.connection-card-select:disabled {
  cursor: default;
  opacity: 0.65;
}
.connection-card-select strong {
  display: block;
  font-size: 14px;
  font-weight: 550;
  overflow-wrap: anywhere;
}
.connection-card-selection {
  display: block;
  margin-bottom: 7px;
  color: var(--text-muted);
  font-size: 10px;
  letter-spacing: 0.5px;
}
.is-selected .connection-card-selection {
  color: var(--brand);
}
.connection-card-meta {
  margin: 10px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
}
.connection-card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
}
.connection-card-key {
  color: var(--text-muted);
  font-size: 11px;
}
.connection-card-footer .config-actions {
  margin-left: auto;
  gap: 0;
}
.connection-card-footer .ui-button {
  gap: 4px;
  padding: 5px 7px;
  font-size: 11px;
}
</style>
