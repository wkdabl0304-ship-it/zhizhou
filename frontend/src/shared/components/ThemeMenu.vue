<!-- 外观选择器：以两张可键盘选择的主题预览呈现明暗方案，沿用 Reka 单选语义和偏好存储。 -->
<script setup lang="ts">
import { ChevronDown, Moon, Sun } from '@lucide/vue'
import { useThemeStore } from '@/shared/stores/theme'
import UiDropdownMenu from '@/shared/components/ui/UiDropdownMenu.vue'
import UiIconButton from '@/shared/components/ui/UiIconButton.vue'
import ThemeOptions from './ThemeOptions.vue'
defineProps<{ compact?: boolean }>()
const theme = useThemeStore()
</script>
<template>
  <UiDropdownMenu :content-props="{ side: 'top', align: 'start', class: 'appearance-menu' }">
    <template #trigger>
      <UiIconButton v-if="compact" label="选择外观"
        ><Sun v-if="theme.theme === 'light'" :size="19" /><Moon v-else :size="19"
      /></UiIconButton>
      <button v-else type="button" class="theme-trigger">
        <span class="theme-trigger-icon"
          ><Sun v-if="theme.theme === 'light'" :size="16" /><Moon v-else :size="16"
        /></span>
        <span>外观</span
        ><span class="theme-trigger-value">{{ theme.theme === 'light' ? '浅色' : '深色' }}</span
        ><ChevronDown class="theme-trigger-chevron" :size="13" aria-hidden="true" />
      </button>
    </template>
    <ThemeOptions />
  </UiDropdownMenu>
</template>
<style>
/* Portal 挂在文档根，选择器仅使用主题变量，预览本身展示各自固定的配色样本。 */
.appearance-menu {
  width: min(278px, calc(100vw - 24px));
  padding: 0;
  border-radius: 16px;
  overflow: hidden;
}
.theme-trigger {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  min-height: 42px;
  padding: 6px 9px;
  border: 1px solid transparent;
  border-radius: 10px;
  background: transparent;
  font: inherit;
  font-size: 12px;
  text-align: left;
  color: var(--text-secondary);
  cursor: pointer;
}
.theme-trigger:hover,
.theme-trigger[data-state='open'] {
  background: var(--surface-hover);
  color: var(--text);
}
.theme-trigger:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: 2px;
}
.theme-trigger-icon {
  display: grid;
  place-items: center;
  width: 27px;
  height: 27px;
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--accent);
  background: var(--surface);
}
.theme-trigger-value {
  margin-left: auto;
  padding: 3px 7px;
  border-radius: 5px;
  background: var(--surface);
  color: var(--text-secondary);
  font-size: 10px;
}
.theme-trigger-chevron {
  transition: transform var(--duration-fast);
}
.theme-trigger[data-state='open'] .theme-trigger-chevron {
  transform: rotate(180deg);
}
@media (prefers-reduced-motion: reduce) {
  .theme-trigger-chevron {
    transition: none;
  }
}
</style>
