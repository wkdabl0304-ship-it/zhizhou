<!-- 工作区账号菜单：头像与用户名作为唯一入口，外观按需展开，复用现有认证与主题状态。 -->
<script setup lang="ts">
import { ref, useId, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ChevronUp, LogOut, PanelsTopLeft, Palette } from '@lucide/vue'
import { DropdownMenuItem, DropdownMenuSeparator } from 'reka-ui'
import BrandLogo from '@/shared/components/BrandLogo.vue'
import ThemeOptions from '@/shared/components/ThemeOptions.vue'
import UiDropdownMenu from '@/shared/components/ui/UiDropdownMenu.vue'
import { useThemeStore } from '@/shared/stores/theme'
import { useAuthStore } from '../store'

const props = defineProps<{ compact?: boolean }>()
const auth = useAuthStore()
const theme = useThemeStore()
const route = useRoute()
const open = ref(false)
const appearanceOpen = ref(false)
const appearanceId = useId()
const isDev = import.meta.env.DEV

/** 展开或收起当前菜单里的外观选项，不关闭账号菜单或提前更改主题。 */
function toggleAppearance(): void {
  appearanceOpen.value = !appearanceOpen.value
}

// 每次重新打开账号菜单都先呈现紧凑列表，不保留上一次展开的大块预览。
watch(open, (value) => {
  if (!value) appearanceOpen.value = false
})

// 位置、身份或侧栏形态变化后收起旧菜单，避免浮层留在已经改变的上下文。
watch([() => route.fullPath, () => auth.accessToken, () => props.compact], () => {
  open.value = false
})
</script>

<template>
  <div class="account-menu" :class="{ 'account-menu--compact': compact }">
    <UiDropdownMenu
      v-model:open="open"
      :content-props="{ side: 'top', align: 'start', class: 'account-menu-panel' }"
    >
      <template #trigger>
        <button
          type="button"
          class="sidebar-profile"
          aria-label="账号菜单"
          :title="auth.user?.username"
        >
          <span class="profile-avatar"><BrandLogo :size="23" /></span>
          <span class="profile-details">
            <span class="profile-name">{{ auth.user?.username ?? '知舟工作空间' }}</span>
            <small v-if="auth.user?.department">{{ auth.user.department.name }}</small>
          </span>
          <ChevronUp class="profile-chevron" :size="15" aria-hidden="true" />
        </button>
      </template>
      <DropdownMenuItem
        class="ui-menu-item account-menu-item account-appearance-trigger"
        aria-label="外观"
        :aria-expanded="appearanceOpen"
        :aria-controls="appearanceOpen ? appearanceId : undefined"
        @select.prevent="toggleAppearance"
      >
        <Palette :size="17" aria-hidden="true" />外观
        <span class="account-menu-current" aria-hidden="true">{{
          theme.theme === 'light' ? '浅色' : '深色'
        }}</span>
        <ChevronUp class="account-appearance-chevron" :size="14" aria-hidden="true" />
      </DropdownMenuItem>
      <div v-if="appearanceOpen" :id="appearanceId">
        <ThemeOptions :show-heading="false" />
      </div>
      <DropdownMenuSeparator v-if="isDev || auth.user" class="account-menu-separator" />
      <DropdownMenuItem v-if="isDev" as-child>
        <RouterLink class="ui-menu-item account-menu-item" to="/dev/ui">
          <PanelsTopLeft :size="17" aria-hidden="true" />组件预览
        </RouterLink>
      </DropdownMenuItem>
      <DropdownMenuItem
        v-if="auth.user"
        class="ui-menu-item account-menu-item"
        @select="auth.logout"
      >
        <LogOut :size="17" aria-hidden="true" />退出登录
      </DropdownMenuItem>
    </UiDropdownMenu>
  </div>
</template>

<style scoped>
.account-menu {
  margin-top: 12px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
}
.sidebar-profile {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-height: 58px;
  padding: 9px 8px;
  border: 1px solid transparent;
  border-radius: 12px;
  background: transparent;
  color: var(--text);
  text-align: left;
  font: inherit;
  cursor: pointer;
}
.sidebar-profile:hover,
.sidebar-profile[data-state='open'] {
  border-color: var(--border);
  background: var(--surface-hover);
}
.sidebar-profile:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: 2px;
}
.profile-avatar {
  display: grid;
  flex-shrink: 0;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: var(--brand-soft);
}
.profile-details {
  display: grid;
  gap: 4px;
  flex: 1;
  min-width: 0;
}
.profile-name,
.profile-details small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.profile-name {
  font-size: 12px;
}
.profile-details small {
  color: var(--text-muted);
  font-size: 10px;
}
.profile-chevron {
  flex-shrink: 0;
  color: var(--text-muted);
  transition: transform var(--duration-fast);
}
.sidebar-profile[data-state='open'] .profile-chevron {
  transform: rotate(180deg);
}
.account-menu--compact {
  border-top: 0;
  padding-top: 0;
}
.account-menu--compact .sidebar-profile {
  justify-content: center;
  min-height: 46px;
  padding: 6px;
}
.account-menu--compact .profile-details,
.account-menu--compact .profile-chevron {
  display: none;
}
@media (prefers-reduced-motion: reduce) {
  .profile-chevron {
    transition: none;
  }
}
</style>

<style>
/* 菜单由 Portal 挂到根节点，沿用共享主题预览样式，尺寸受视口及 Reka 可用高度约束。 */
.account-menu-panel {
  width: min(278px, calc(100vw - 24px));
  padding: 7px 0;
  border-radius: 16px;
}
.account-menu-separator {
  height: 1px;
  margin: 1px 13px 7px;
  background: var(--border);
}
.account-menu-item {
  margin: 2px 7px;
  min-height: 42px;
  padding: 10px 12px;
  text-decoration: none;
  color: var(--text-secondary);
  cursor: pointer;
}
.account-menu-item svg {
  color: var(--text-muted);
}
.account-menu-current {
  margin-left: auto;
  color: var(--text-muted);
  font-size: 11px;
}
.account-appearance-chevron {
  transform: rotate(180deg);
}
.account-appearance-trigger[aria-expanded='true'] .account-appearance-chevron {
  transform: none;
}
</style>
