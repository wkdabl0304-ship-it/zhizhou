<!-- 自适应文本框：保留原生输入与属性透传，仅负责高度计算；发送策略由业务输入区决定。 -->
<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const model = defineModel<string>({ default: '' })
withDefaults(defineProps<{ label: string; placeholder?: string; disabled?: boolean }>(), {
  placeholder: '',
})
const element = ref<HTMLTextAreaElement>()
let observer: ResizeObserver | undefined
let lastWidth = 0

/**
 * 根据当前内容调整文本框高度，让草稿在输入区内自然展开。
 * 等待 DOM 更新后清除旧高度并测量 scrollHeight；最大高度由公共样式限制，
 * 超出上限后使用文本框内部滚动，不修改输入内容。
 */
async function resize(): Promise<void> {
  await nextTick()
  if (!element.value) return
  element.value.style.height = 'auto'
  element.value.style.height = `${element.value.scrollHeight}px`
}

/** 聚焦原生文本框，供上层输入组件在填入建议或切换页面后继续输入。 */
function focus(): void {
  element.value?.focus()
}

watch(model, resize)
// 首次挂载时计算高度并监听宽度变化，补上自动换行导致的高度调整。
onMounted(() => {
  resize()
  if (typeof ResizeObserver === 'undefined') return
  // 仅在宽度改变时重测高度，避免自己的高度变化再次触发测量循环。
  observer = new ResizeObserver((entries) => {
    const width = entries[0]?.contentRect.width
    if (width !== undefined && width !== lastWidth) {
      lastWidth = width
      resize()
    }
  })
  if (element.value) observer.observe(element.value)
})
// 页面切换与条件卸载时释放观察器，避免持有已移除的输入节点。
onBeforeUnmount(() => observer?.disconnect())
defineExpose({ focus })
</script>

<template>
  <textarea
    ref="element"
    v-model="model"
    class="ui-textarea"
    rows="1"
    :aria-label="label"
    :placeholder="placeholder"
    :disabled="disabled"
  />
</template>
