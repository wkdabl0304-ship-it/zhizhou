<!-- 模型管理页面：展示供应商品牌卡片，具体配置由供应商弹窗负责。 -->
<script setup lang="ts">
import UiFeedback from '@/shared/components/ui/UiFeedback.vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useModelConfigStore } from '@/features/model-config/store'
import type { ProviderInfo } from '@/features/model-config/types'
import ProviderCard from '@/features/model-config/components/ProviderCard.vue'
import ProviderDialog from '@/features/model-config/components/ProviderDialog.vue'
import '@/features/model-config/model-config.css'
import UiPageHeader from '@/shared/components/ui/UiPageHeader.vue'
const store = useModelConfigStore()
const activeBrand = ref<ProviderInfo | null>(null)
const brandOrder = ['openai', 'anthropic', 'deepseek', 'bailian']
const brands = computed(() =>
  [...store.brands].sort(
    (left, right) => brandOrder.indexOf(left.provider) - brandOrder.indexOf(right.provider),
  ),
)
// 管理页加载共享快照，退出时释放请求而不影响聊天摘要缓存。
onMounted(() => {
  void store.load()
})
onBeforeUnmount(() => store.cancelManagement())
</script>
<template>
  <section class="model-management-main" aria-label="模型管理工作区">
    <div class="config-page">
      <UiPageHeader class="model-management-title-row" title="模型管理" size="lg" serif />
      <section aria-label="供应商配置列表">
        <div class="config-section-heading provider-grid-heading">
          <h2>
            模型供应商 <small>{{ brands.length }}</small>
          </h2>
          <span class="config-hint">所有登录用户共享配置</span>
        </div>
        <UiFeedback v-if="store.loadError">
          {{ store.loadError }}，请稍后重新进入页面。
        </UiFeedback>
        <p v-if="store.loading && !store.selected" role="status">正在读取模型配置…</p>
        <div class="provider-brand-grid">
          <ProviderCard
            v-for="brand in brands"
            :key="brand.provider"
            :brand="brand"
            :connections="store.configurations.filter((item) => item.provider === brand.provider)"
            :models="store.models"
            @open="activeBrand = brand"
          />
        </div>
      </section>
      <ProviderDialog
        v-if="activeBrand"
        :key="activeBrand.provider"
        :brand="activeBrand"
        @close="activeBrand = null"
      />
    </div>
  </section>
</template>
