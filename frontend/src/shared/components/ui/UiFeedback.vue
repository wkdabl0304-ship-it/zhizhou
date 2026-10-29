<!-- 全局失败反馈：统一错误语义与视觉；调用方控制出现、清除及重试，不生成成功通知。 -->
<script setup lang="ts">
import { CircleAlert, RotateCcw } from '@lucide/vue'
import UiButton from './UiButton.vue'

withDefaults(
  defineProps<{
    message?: string
    title?: string
    compact?: boolean
    retryLabel?: string
    busy?: boolean
  }>(),
  { message: '', title: '', retryLabel: '' },
)
const emit = defineEmits<{ retry: [] }>()
</script>

<template>
  <div class="ui-feedback" :class="{ 'ui-feedback--compact': compact }" role="alert">
    <CircleAlert :size="compact ? 15 : 18" aria-hidden="true" />
    <div class="ui-feedback-content">
      <strong v-if="title">{{ title }}</strong>
      <div>
        <slot>{{ message }}</slot>
      </div>
    </div>
    <div v-if="retryLabel || $slots.actions" class="ui-feedback-actions">
      <slot name="actions">
        <UiButton size="sm" :loading="busy" @click="emit('retry')">
          <RotateCcw :size="14" aria-hidden="true" />{{ retryLabel }}
        </UiButton>
      </slot>
    </div>
  </div>
</template>
