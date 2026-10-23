<!-- 知舟品牌标志：通过青蓝舟形 SVG 与主题语义变量，统一侧栏、首页与消息头像。 -->
<script setup lang="ts">
import riverMark from '@/assets/brand/mark-river.svg?raw'
withDefaults(defineProps<{ size?: number; decorative?: boolean }>(), { size: 32, decorative: true })
</script>
<template>
  <span
    class="brand-logo"
    :style="{ width: `${size}px`, height: `${size}px` }"
    :role="decorative ? undefined : 'img'"
    :aria-hidden="decorative || undefined"
    :aria-label="decorative ? undefined : '知舟：舟与航迹标志'"
    v-html="riverMark"
  />
</template>
<style scoped>
.brand-logo {
  display: inline-flex;
  flex-shrink: 0;
  vertical-align: middle;
  color: var(--text);
}
.brand-logo :deep(svg) {
  display: block;
  width: 100%;
  height: 100%;
}
.brand-logo :deep(.mark-accent) {
  fill: var(--brand);
}
.brand-logo :deep(.mark-accent-stroke) {
  stroke: var(--brand);
}
</style>
