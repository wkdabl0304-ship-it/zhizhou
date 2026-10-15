<!-- 外观菜单：以 Reka 单选菜单表达当前主题，统一鼠标与键盘选择行为。 -->
<script setup lang="ts">
import { Check, ChevronDown, Moon, Sun } from '@lucide/vue'
import {
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuItemIndicator,
} from 'reka-ui'
import { useThemeStore, type Theme } from '@/stores/theme'
import UiDropdownMenu from '@/components/ui/UiDropdownMenu.vue'
import UiIconButton from '@/components/ui/UiIconButton.vue'

defineProps<{ compact?: boolean }>()
const theme = useThemeStore()

/** 只接收菜单中定义的合法值，避免将未知字符串写入全局主题。 */
function update(value: unknown): void {
  if (value === 'light' || value === 'dark') theme.setTheme(value as Theme)
}
</script>

<template>
  <UiDropdownMenu :content-props="{ side: 'top', align: 'start' }">
    <template #trigger>
      <UiIconButton v-if="compact" label="选择外观"
        ><Sun v-if="theme.theme === 'light'" :size="19" /><Moon v-else :size="19"
      /></UiIconButton>
      <button v-else type="button" class="theme-trigger">
        <span class="theme-trigger-icon"
          ><Sun v-if="theme.theme === 'light'" :size="17" /><Moon v-else :size="17" /></span
        ><span>外观</span
        ><span class="theme-trigger-value">{{ theme.theme === 'light' ? '浅色' : '深色' }}</span
        ><ChevronDown :size="14" />
      </button>
    </template>
    <DropdownMenuLabel class="ui-menu-label">外观偏好</DropdownMenuLabel>
    <DropdownMenuRadioGroup :model-value="theme.theme" @update:model-value="update">
      <DropdownMenuRadioItem class="ui-menu-item" value="light"
        ><Sun :size="16" />浅色<DropdownMenuItemIndicator class="ui-menu-indicator"
          ><Check :size="15" /></DropdownMenuItemIndicator
      ></DropdownMenuRadioItem>
      <DropdownMenuRadioItem class="ui-menu-item" value="dark"
        ><Moon :size="16" />深色<DropdownMenuItemIndicator class="ui-menu-indicator"
          ><Check :size="15" /></DropdownMenuItemIndicator
      ></DropdownMenuRadioItem>
    </DropdownMenuRadioGroup>
  </UiDropdownMenu>
</template>
