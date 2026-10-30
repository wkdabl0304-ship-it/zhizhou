<!-- 外观选择器：以两张可键盘选择的主题预览呈现明暗方案，沿用 Reka 单选语义和偏好存储。 -->
<script setup lang="ts">
import { Check, ChevronDown, Moon, Sun, Palette } from '@lucide/vue'
import {
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuItemIndicator,
} from 'reka-ui'
import { useThemeStore, type Theme } from '@/shared/stores/theme'
import UiDropdownMenu from '@/shared/components/ui/UiDropdownMenu.vue'
import UiIconButton from '@/shared/components/ui/UiIconButton.vue'

defineProps<{ compact?: boolean }>()
const theme = useThemeStore()
const schemes = [
  { value: 'light', label: '浅色', name: '青碧 · 朱砂', icon: Sun },
  { value: 'dark', label: '深色', name: '靛夜 · 月金', icon: Moon },
] as const
/** 只接受产品支持的主题值，立即更新页面及 Portal，并沿用已有存储规则。 */
function update(value: unknown): void {
  if (value === 'light' || value === 'dark') theme.setTheme(value as Theme)
}
/** 左右键按双列视觉顺序浏览，Enter 才应用，保留菜单原有的上下键与 Esc 交互。 */
function navigate(event: KeyboardEvent): void {
  if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
  event.preventDefault()
  event.stopPropagation()
  const items = [
    ...(event.currentTarget as HTMLElement).querySelectorAll<HTMLElement>('[role="menuitemradio"]'),
  ]
  if (!items.length) return
  const index = items.indexOf(document.activeElement as HTMLElement)
  items[(index + (event.key === 'ArrowRight' ? 1 : -1) + items.length) % items.length]?.focus()
}
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
    <DropdownMenuLabel class="appearance-heading"
      ><span><Palette :size="15" aria-hidden="true" />外观</span></DropdownMenuLabel
    >
    <DropdownMenuRadioGroup
      class="appearance-options"
      aria-label="外观配色方案"
      :model-value="theme.theme"
      @update:model-value="update"
      @keydown="navigate"
    >
      <DropdownMenuRadioItem
        v-for="scheme in schemes"
        :key="scheme.value"
        class="appearance-option"
        :value="scheme.value"
        :aria-label="scheme.label"
      >
        <span
          class="appearance-preview"
          :class="`appearance-preview--${scheme.value}`"
          aria-hidden="true"
          ><span class="appearance-preview-rail"><i /><i /><i /></span
          ><span class="appearance-preview-scene"
            ><span class="appearance-preview-mountain" /><span
              class="appearance-preview-composer" /></span
        ></span>
        <span class="appearance-option-title"
          ><component :is="scheme.icon" :size="14" aria-hidden="true" /><span>{{
            scheme.label
          }}</span
          ><span class="appearance-check"
            ><DropdownMenuItemIndicator
              ><Check :size="12" aria-hidden="true" /></DropdownMenuItemIndicator></span
        ></span>
        <span class="appearance-option-caption">{{ scheme.name }}</span>
      </DropdownMenuRadioItem>
    </DropdownMenuRadioGroup>
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
.appearance-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 15px 16px 12px;
  border-bottom: 1px solid var(--border);
}
.appearance-heading > span {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--text);
  font-size: 13px;
  font-weight: 500;
}
.appearance-heading svg {
  color: var(--accent);
}
.appearance-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  padding: 13px;
}
.appearance-option {
  min-width: 0;
  padding: 7px;
  border: 1px solid var(--border);
  border-radius: 10px;
  cursor: pointer;
  outline: none;
  color: var(--text-secondary);
}
.appearance-option[data-highlighted] {
  background: var(--surface-hover);
  box-shadow: 0 0 0 2px var(--brand);
}
.appearance-option[data-state='checked'] {
  border-color: var(--brand);
  background: var(--brand-soft);
  color: var(--text);
}
.appearance-preview {
  display: flex;
  overflow: hidden;
  height: 64px;
  border: 1px solid rgb(34 71 66 / 13%);
  border-radius: 6px;
  background: #f5f8f5;
}
.appearance-preview-rail {
  width: 19%;
  flex-shrink: 0;
  padding: 10px 4px;
  background: #dcebe5;
}
.appearance-preview-rail i {
  display: block;
  height: 2px;
  margin-bottom: 5px;
  border-radius: 2px;
  background: #7ca99c;
}
.appearance-preview-rail i:first-child {
  width: 70%;
  margin-bottom: 9px;
  background: #b24c2e;
}
.appearance-preview-scene {
  position: relative;
  flex: 1;
  overflow: hidden;
  background: linear-gradient(180deg, #f5f8f5 35%, #c1e1d7);
}
.appearance-preview-mountain {
  position: absolute;
  width: 60%;
  height: 36px;
  right: -3px;
  bottom: 0;
  border-radius: 70% 0 0;
  transform: rotate(-15deg);
  background: #69a89e;
  opacity: 0.55;
}
.appearance-preview-composer {
  position: absolute;
  left: 12%;
  right: 10%;
  bottom: 9px;
  height: 15px;
  border: 1px solid #adcbc0;
  border-radius: 4px;
  background: #ffffff;
  box-shadow: 0 2px 6px rgb(0 50 40 / 8%);
}
.appearance-preview--dark {
  border-color: #405775;
  background: #101a2b;
}
.appearance-preview--dark .appearance-preview-rail {
  background: #0c1524;
}
.appearance-preview--dark .appearance-preview-rail i {
  background: #49647b;
}
.appearance-preview--dark .appearance-preview-rail i:first-child {
  background: #e9bd7e;
}
.appearance-preview--dark .appearance-preview-scene {
  background: linear-gradient(180deg, #101a2b 35%, #233c55);
}
.appearance-preview--dark .appearance-preview-mountain {
  background: #40797d;
}
.appearance-preview--dark .appearance-preview-composer {
  border-color: #4a617d;
  background: #1b2940;
}
.appearance-option-title {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 10px;
  font-size: 12px;
  font-weight: 500;
}
.appearance-check {
  display: grid;
  place-items: center;
  width: 15px;
  height: 15px;
  margin-left: auto;
  border: 1px solid var(--border-strong);
  border-radius: 50%;
  color: var(--brand-contrast);
}
.appearance-option[data-state='checked'] .appearance-check {
  border-color: var(--brand);
  background: var(--brand);
}
.appearance-option-caption {
  display: block;
  margin-top: 5px;
  color: var(--text-muted);
  font-size: 10px;
  white-space: nowrap;
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
