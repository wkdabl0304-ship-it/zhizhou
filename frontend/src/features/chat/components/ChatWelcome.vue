<!-- 首页组合：青蓝水墨标题区、适中尺寸的真实输入区；通过事件交出用户输入，不直接依赖聊天 store。 -->
<script setup lang="ts">
import { ref } from 'vue'
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
      <ChatComposer
        ref="composer"
        v-model="model"
        :sending="sending"
        :send-blocked="sendBlocked"
        @send="$emit('send', $event)"
        ><template #reasoning-controls><slot name="reasoning-controls" /></template
        ><template #model-selector><slot name="model-selector" /></template
      ></ChatComposer>
      <p class="welcome-foot">AI 回复仅供参考</p>
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
.welcome-foot {
  margin: 14px 0 0;
  text-align: center;
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
