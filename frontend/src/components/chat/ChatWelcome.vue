<!-- 首页组合：青蓝水墨标题区、真实输入区和建议问题；通过事件交出用户输入，不直接依赖聊天 store。 -->
<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { ArrowUpRight } from '@lucide/vue'
import { suggestions } from '@/data/demo'
import BrandLogo from '@/components/BrandLogo.vue'
import ChatComposer from './ChatComposer.vue'
import RiverWelcomeHero from './RiverWelcomeHero.vue'
const model = defineModel<string>({ default: '' })
defineProps<{ sending?: boolean }>()
defineEmits<{ send: [text: string] }>()
const composer = ref<InstanceType<typeof ChatComposer>>()
/** 填入建议但不发送；DOM 同步后将焦点送回输入区，供用户继续编辑。 */
async function fillSuggestion(prompt: string): Promise<void> {
  model.value = prompt
  await nextTick()
  composer.value?.focus()
}
/** 暴露与输入区一致的焦点入口，供页面切换后恢复连续输入。 */
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
        @send="$emit('send', $event)"
      />
      <div class="suggestions">
        <button
          v-for="suggestion in suggestions"
          :key="suggestion.title"
          type="button"
          class="suggestion"
          @click="fillSuggestion(suggestion.prompt)"
        >
          <span>{{ suggestion.title }}</span
          ><ArrowUpRight :size="15" />
        </button>
      </div>
      <div class="welcome-foot"><span>让工作，始于一句话。</span><span>AI 回复仅供参考</span></div>
    </div>
  </section>
</template>
<style scoped>
.welcome {
  width: min(100%, 1100px);
  margin: auto;
  padding: 0 24px 24px;
}
.welcome-controls {
  position: relative;
  z-index: 1;
  max-width: var(--content-width);
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
.suggestions {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-top: 18px;
}
.suggestion {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-width: 0;
  padding: 11px 12px;
  border: 1px solid var(--border-strong);
  border-radius: 30px;
  background: color-mix(in srgb, var(--bg) 90%, transparent);
  color: var(--text);
  font-size: 12px;
  transition:
    border-color 160ms,
    background 160ms;
}
.suggestion:hover {
  border-color: var(--brand);
  background: var(--brand-soft);
}
.suggestion svg {
  color: var(--brand);
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
  .suggestions {
    grid-template-columns: 1fr;
    gap: 7px;
    margin-top: 16px;
  }
  .suggestion {
    padding: 9px 12px;
    font-size: 11px;
  }
  .welcome-foot {
    font-size: 9px;
  }
}
</style>
