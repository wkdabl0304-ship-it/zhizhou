<!-- 首页组合：青蓝水墨标题区、适中尺寸的真实输入区；通过事件交出用户输入，不直接依赖聊天 store。 -->
<script setup lang="ts">
import { ref } from 'vue'
import BrandLogo from '@/shared/components/BrandLogo.vue'
import ChatComposer from './ChatComposer.vue'
import RiverWelcomeHero from './RiverWelcomeHero.vue'
const model = defineModel<string>({ default: '' })
defineProps<{ sending?: boolean; sendBlocked?: boolean }>()
defineEmits<{ send: [text: string] }>()
const composer = ref<InstanceType<typeof ChatComposer>>()
/** 聚焦首页聊天输入区，供父页面在界面切换后恢复连续输入。 */
function focus(): void {
  composer.value?.focus()
}
defineExpose({ focus })
</script>
<template>
  <section class="welcome" aria-label="开启新对话">
    <RiverWelcomeHero />
    <div class="welcome-controls">
      <div class="welcome-composer-label">
        <BrandLogo :size="20" /><span>把你的想法，交给知舟</span>
      </div>
      <ChatComposer
        ref="composer"
        v-model="model"
        :sending="sending"
        :send-blocked="sendBlocked"
        @send="$emit('send', $event)"
        ><template #reasoning-controls><slot name="reasoning-controls" /></template
        ><template #model-selector><slot name="model-selector" /></template
      ></ChatComposer>
      <div class="welcome-foot"><span>让工作，始于一句话。</span><span>AI 回复仅供参考</span></div>
    </div>
  </section>
</template>
<style scoped>
.welcome {
  width: min(100%, 1200px);
  margin: clamp(24px, 5dvh, 56px) auto auto;
  padding: 0 24px 24px;
}
.welcome-controls {
  position: relative;
  z-index: 1;
  max-width: 860px;
  margin: 0 auto;
}
.welcome-composer-label {
  display: flex;
  width: fit-content;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 4px 12px;
  margin: 0 auto 11px;
  border: 1px solid var(--border);
  border-radius: 30px;
  background: var(--bg);
  color: var(--text);
  font-size: 11px;
}
.welcome-foot {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding-top: 19px;
  color: var(--text-muted);
  font-size: 10px;
}
@media (max-width: 760px) {
  .welcome {
    padding: 0 20px 22px;
  }
  .welcome-foot {
    font-size: 9px;
  }
}
</style>
