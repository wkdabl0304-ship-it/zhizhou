<!-- 全局静态标签：以统一的墨色边界、语义色与尺寸展示身份、归属和状态，不承担交互。 -->
<script setup lang="ts">
withDefaults(
  defineProps<{
    tone?: 'neutral' | 'brand' | 'accent' | 'danger'
    /** 按使用密度选择留白：xs 行内、sm 列表、md 卡片、lg 重点状态。 */
    size?: 'xs' | 'sm' | 'md' | 'lg'
    dot?: boolean
  }>(),
  { tone: 'neutral', size: 'sm' },
)
</script>

<template>
  <span class="ui-tag" :class="[`ui-tag--${tone}`, `ui-tag--${size}`]">
    <span v-if="dot" class="ui-tag-dot" aria-hidden="true" />
    <slot />
  </span>
</template>
