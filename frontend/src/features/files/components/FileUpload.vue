<!-- 工具栏上传按钮：保留原生多文件选择与键盘入口，传输和拖放由页面统一编排。 -->
<script setup lang="ts">
import { ref } from 'vue'
import { Upload, X } from '@lucide/vue'
import UiButton from '@/shared/components/ui/UiButton.vue'

defineProps<{ busy: boolean; disabled?: boolean }>()
const emit = defineEmits<{ files: [files: File[]]; cancel: [] }>()
const input = ref<HTMLInputElement>()

/** 交付本次文件选择并立即清空原生值，使同名文件仍可再次主动选择。 */
function select(event: Event): void {
  const element = event.target as HTMLInputElement
  const files = Array.from(element.files ?? [])
  element.value = ''
  emit('files', files)
}
</script>
<template>
  <span class="file-upload">
    <input
      ref="input"
      type="file"
      multiple
      class="file-input"
      aria-label="选择上传文件"
      tabindex="-1"
      :disabled="busy || disabled"
      @change="select"
    />
    <UiButton
      :variant="busy ? 'secondary' : 'primary'"
      size="sm"
      :disabled="disabled && !busy"
      @click="busy ? emit('cancel') : input?.click()"
    >
      <X v-if="busy" :size="15" /><Upload v-else :size="16" />{{ busy ? '中止上传' : '上传文件' }}
    </UiButton>
  </span>
</template>
