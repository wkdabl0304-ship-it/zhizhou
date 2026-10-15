<!-- 品牌标志预览：原始 SVG 仅来自本地受信配置，禁止向此组件传入外部 SVG 或运行时 HTML。 -->
<script setup lang="ts">
import { computed } from 'vue'
import { brandDesigns, type BrandId } from './designs'

const props = withDefaults(
  defineProps<{
    variant: BrandId
    size?: number
    tone?: 'brand' | 'ink' | 'reverse'
    decorative?: boolean
  }>(),
  { size: 32, tone: 'brand', decorative: true },
)
// SVG 是仓库内固定导入的原创资产，不拼接用户内容；统一来源避免组件与下载文件形状不一致。
const source = computed(() => brandDesigns.find((design) => design.id === props.variant)!.mark)
</script>

<template>
  <span
    class="brand-glyph"
    :class="`brand-glyph--${tone}`"
    :style="{ width: `${size}px`, height: `${size}px` }"
    :role="decorative ? undefined : 'img'"
    :aria-hidden="decorative || undefined"
    :aria-label="decorative ? undefined : '知舟：舟与航迹标志'"
    v-html="source"
  />
</template>

<style scoped>
.brand-glyph {
  display: inline-flex;
  flex-shrink: 0;
  color: inherit;
  vertical-align: middle;
}
.brand-glyph :deep(svg) {
  display: block;
  width: 100%;
  height: 100%;
}
.brand-glyph--brand :deep(.mark-accent) {
  fill: var(--b-accent, #bb3a2f);
}
.brand-glyph--brand :deep(.mark-accent-stroke) {
  stroke: var(--b-accent, #bb3a2f);
}
.brand-glyph--ink {
  color: #171714;
}
.brand-glyph--reverse {
  color: #f7f7f3;
}
</style>
