<!-- 模型切换分隔线：展示后续轮次使用的模型变化，作为对话记录的一部分而非成功通知。 -->
<script setup lang="ts">
import { Box, Info } from '@lucide/vue'
import UiTooltip from '@/shared/components/ui/UiTooltip.vue'
import type { ModelIdentity } from '@/features/model-selection/types'
defineProps<{ from: ModelIdentity; to: ModelIdentity }>()
</script>
<template>
  <div
    class="model-change-notice"
    role="separator"
    :aria-label="`模型已从 ${from.display_name} 切换为 ${to.display_name}`"
  >
    <Box :size="15" aria-hidden="true" />
    <span class="model-change-copy"
      >模型已从 {{ from.display_name }} 切换为 {{ to.display_name }}</span
    >
    <UiTooltip text="此轮起使用切换后的模型，已有消息保持不变。">
      <button class="model-change-info" type="button" aria-label="模型切换说明">
        <Info :size="13" aria-hidden="true" />
      </button>
    </UiTooltip>
  </div>
</template>
<style scoped>
.model-change-notice {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  margin: 28px 0;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.7;
}
.model-change-notice::before,
.model-change-notice::after {
  content: '';
  flex: 1;
  min-width: 16px;
  height: 1px;
  background: var(--border);
}
.model-change-notice > svg {
  flex-shrink: 0;
}
.model-change-copy {
  overflow-wrap: anywhere;
  text-align: center;
}
.model-change-info {
  display: inline-flex;
  padding: 3px;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: help;
  flex-shrink: 0;
  border-radius: 4px;
}
.model-change-info:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: 2px;
}
@media (max-width: 540px) {
  .model-change-notice {
    gap: 6px;
    font-size: 11px;
    margin: 24px 0;
  }
}
</style>
