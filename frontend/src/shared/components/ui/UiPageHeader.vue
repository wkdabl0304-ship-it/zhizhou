<!-- 通用页面标题：配置字号、眉题、说明、对齐和标题级别，前置入口与操作通过插槽组合。 -->
<script setup lang="ts">
import { ref } from 'vue'
withDefaults(
  defineProps<{
    title: string
    eyebrow?: string
    description?: string
    size?: 'sm' | 'md' | 'lg'
    level?: 1 | 2 | 3
    align?: 'start' | 'center'
    truncate?: boolean
    editable?: boolean
    serif?: boolean
  }>(),
  { size: 'md', level: 1, align: 'start' },
)
defineEmits<{ titleDblclick: [event: MouseEvent] }>()
const titleElement = ref<HTMLElement>()
/** 将焦点交回真实标题，供抽屉关闭或原操作入口移除后的页面恢复使用。 */
function focus(): void {
  titleElement.value?.focus()
}
defineExpose({ focus, titleElement })
</script>
<template>
  <header class="ui-page-header" :class="[`ui-page-header--${size}`, `ui-page-header--${align}`]">
    <slot name="before" />
    <div class="ui-page-heading">
      <p v-if="eyebrow" class="ui-page-eyebrow">{{ eyebrow }}</p>
      <component
        :is="`h${level}`"
        ref="titleElement"
        tabindex="-1"
        class="ui-page-title header-title"
        :class="{ 'is-truncated': truncate, 'is-editable': editable, 'is-serif': serif }"
        :title="truncate ? title : undefined"
        @dblclick="$emit('titleDblclick', $event)"
        >{{ title }}</component
      >
      <p v-if="description" class="ui-page-description">{{ description }}</p>
    </div>
    <div v-if="$slots.actions" class="ui-page-header-actions"><slot name="actions" /></div>
  </header>
</template>
<style scoped>
.ui-page-header {
  display: flex;
  align-items: center;
  gap: 16px;
  min-width: 0;
}
.ui-page-heading {
  min-width: 0;
  flex: 1;
}
.ui-page-title {
  margin: 0;
  color: var(--text);
  font-size: 22px;
  font-weight: 500;
  line-height: 1.35;
}
.ui-page-title:focus {
  outline: none;
}
.ui-page-title.is-serif {
  font-family: 'Noto Serif SC', 'Songti SC', 'SimSun', serif;
  letter-spacing: 1px;
}
.ui-page-title.is-truncated {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ui-page-title.is-editable {
  cursor: text;
}
.ui-page-eyebrow {
  margin: 0 0 5px;
  color: var(--accent);
  font-size: 11px;
  letter-spacing: 1.5px;
}
.ui-page-description {
  margin: 9px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.7;
}
.ui-page-header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}
.ui-page-header--sm .ui-page-title {
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 400;
}
.ui-page-header--lg .ui-page-title {
  font-size: clamp(24px, 2vw, 28px);
}
.ui-page-header--center {
  flex-direction: column;
  text-align: center;
}
@media (max-width: 540px) {
  .ui-page-header {
    gap: 12px;
  }
  .ui-page-header-actions {
    gap: 8px;
  }
}
</style>
