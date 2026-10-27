<!-- 供应商品牌 Logo：复用本地 SVG，单色标志随主题反色，运行时无需外部图片请求。 -->
<script setup lang="ts">
import openai from '@/assets/providers/openai.svg'
import anthropic from '@/assets/providers/anthropic.svg'
import deepseek from '@/assets/providers/deepseek-color.svg'
import bailian from '@/assets/providers/bailian-color.svg'
defineProps<{ provider: 'openai' | 'anthropic' | 'deepseek' | 'bailian' }>()
const sources = { openai, anthropic, deepseek, bailian }
</script>
<template>
  <img
    class="provider-logo"
    :class="{ 'provider-logo--mono': provider === 'openai' || provider === 'anthropic' }"
    :src="sources[provider]"
    alt=""
    aria-hidden="true"
  />
</template>
<style>
/* 品牌类名独立命名，直接匹配主题；滤镜只作用于单色 Logo，不能施加给根元素。 */
.provider-logo {
  display: block;
  flex-shrink: 0;
  width: var(--provider-logo-size, 32px);
  height: var(--provider-logo-size, 32px);
  object-fit: contain;
}
:root[data-theme='dark'] .provider-logo--mono {
  filter: brightness(0) invert(1);
}
</style>
