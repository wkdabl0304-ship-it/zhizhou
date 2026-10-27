<!-- 供应商品牌卡片：汇总安全的连接及启用数量，点击后由页面打开配置弹窗。 -->
<script setup lang="ts">
import { ArrowUpRight } from '@lucide/vue'
import type { ProviderInfo, ProviderConfiguration, ModelConfiguration } from '../types'
import { computed } from 'vue'
import ProviderLogo from '@/shared/components/ProviderLogo.vue'
const props = defineProps<{
  brand: ProviderInfo
  connections: ProviderConfiguration[]
  models: ModelConfiguration[]
}>()
defineEmits<{ open: [] }>()
const enabledCount = computed(
  () =>
    props.models.filter(
      (model) =>
        model.enabled &&
        props.connections.some((connection) => connection.id === model.provider_configuration_id),
    ).length,
)
const connected = computed(() => props.connections.some((connection) => connection.enabled))
const descriptions = {
  openai: 'GPT 系列 · 通用对话与推理',
  anthropic: 'Claude 系列 · 深度思考与创作',
  deepseek: 'DeepSeek 系列 · 高效推理',
  bailian: '通义千问 · 阿里云百炼',
}
</script>
<template>
  <button
    type="button"
    class="provider-brand-card"
    :data-provider="brand.provider"
    :aria-label="`配置 ${brand.display_name}`"
    @click="$emit('open')"
  >
    <div class="provider-card-top">
      <span class="provider-logo-frame"><ProviderLogo :provider="brand.provider" /></span
      ><span class="provider-connection-status" :class="{ 'is-configured': connected }"
        ><i />{{ !connections.length ? '未配置' : connected ? '已配置' : '连接已停用' }}</span
      >
    </div>
    <h3>{{ brand.display_name }}</h3>
    <p>{{ descriptions[brand.provider] }}</p>
    <div class="provider-card-bottom">
      <span
        >{{ enabledCount }} 个模型已启用<span v-if="connections.length > 1">
          · {{ connections.length }} 份连接</span
        ></span
      ><span class="provider-card-entry">配置模型 <ArrowUpRight :size="15" /></span>
    </div>
  </button>
</template>
