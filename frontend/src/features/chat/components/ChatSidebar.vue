<!-- 聊天侧栏：共用于桌面导航与窄屏抽屉，向上报告选择、新建和折叠事件。 -->
<script setup lang="ts">
import { computed } from 'vue'
import { ArrowUpRight, LogOut, PanelLeft, SquarePen, SlidersHorizontal, Users } from '@lucide/vue'
import type { Conversation } from '@/features/chat/types'
import ThemeMenu from '@/shared/components/ThemeMenu.vue'
import BrandLogo from '@/shared/components/BrandLogo.vue'
import UiIconButton from '@/shared/components/ui/UiIconButton.vue'
import UiTooltip from '@/shared/components/ui/UiTooltip.vue'
import ConversationItem from './ConversationItem.vue'
import { useAuthStore } from '@/features/auth/store'
import { canManageOrganization } from '@/features/auth/permissions'

const auth = useAuthStore()

const props = defineProps<{
  conversations: Conversation[]
  activeId: string | null
  compact?: boolean
  drawer?: boolean
  loading?: boolean
  error?: string
  actionError?: string
  hasMore?: boolean
  renamable?: boolean
}>()
defineEmits<{
  select: [id: string]
  new: []
  toggle: []
  more: []
  retry: []
  delete: [id: string, trigger: HTMLElement]
  rename: [id: string, trigger: HTMLElement]
}>()
const isDev = import.meta.env.DEV
// 根据本页会话自身分组，新增会话自动进入“今天”。
const groups = computed(() => [...new Set(props.conversations.map((item) => item.group))])
</script>

<template>
  <div class="chat-sidebar" :class="{ 'is-compact': compact }">
    <div class="sidebar-heading">
      <!-- 品牌图标和文字共用首页入口，由父页面统一清理草稿并关闭窄屏抽屉。 -->
      <button
        type="button"
        class="brand"
        :class="{ 'brand--compact': compact }"
        aria-label="返回首页"
        title="返回首页"
        @click="$emit('new')"
      >
        <BrandLogo :size="compact ? 34 : 39" /><span v-if="!compact" class="brand-name"
          >知舟<span class="brand-en">ZHIZHOU</span></span
        >
      </button>
      <UiTooltip v-if="!drawer && !compact" text="收起侧栏" :content-props="{ side: 'right' }"
        ><UiIconButton label="收起侧栏" @click="$emit('toggle')"
          ><PanelLeft :size="18" /></UiIconButton
      ></UiTooltip>
    </div>
    <UiTooltip v-if="compact" text="展开侧栏" :content-props="{ side: 'right' }"
      ><UiIconButton label="展开侧栏" @click="$emit('toggle')"
        ><PanelLeft :size="19" /></UiIconButton
    ></UiTooltip>
    <UiTooltip v-if="compact" text="新建对话" :content-props="{ side: 'right' }"
      ><UiIconButton label="新建对话" @click="$emit('new')"><SquarePen :size="19" /></UiIconButton
    ></UiTooltip>
    <button v-else type="button" class="new-chat-button" @click="$emit('new')">
      <SquarePen :size="17" /><span>开启新对话</span
      ><span class="new-chat-plus" aria-hidden="true">＋</span>
    </button>
    <nav v-if="!compact" class="conversation-nav" aria-label="会话记录">
      <div class="sidebar-section-label">你的对话</div>
      <p v-if="error" class="directory-error" role="alert">
        {{ error
        }}<button
          type="button"
          class="directory-action"
          :disabled="loading"
          @click="$emit('retry')"
        >
          重试
        </button>
      </p>
      <p v-if="actionError" class="directory-error" role="alert">{{ actionError }}</p>
      <p v-if="loading" class="directory-hint" role="status">正在加载会话…</p>
      <p v-else-if="!conversations.length && !error" class="directory-hint">
        还没有对话，开启一次新的思考。
      </p>
      <section v-for="group in groups" :key="group" class="conversation-group" :aria-label="group">
        <h2>{{ group }}</h2>
        <template v-for="conversation in conversations" :key="conversation.id"
          ><ConversationItem
            v-if="conversation.group === group"
            :title="conversation.title"
            :active="conversation.id === activeId"
            :removable="conversation.persisted"
            :busy="conversation.running || conversation.deleting || conversation.titleSaving"
            :renamable="renamable && conversation.persisted"
            :rename-disabled="
              conversation.deleting || conversation.titleSaving || conversation.unavailable
            "
            @rename="$emit('rename', conversation.id, $event)"
            @select="$emit('select', conversation.id)"
            @delete="$emit('delete', conversation.id, $event)"
        /></template>
      </section>
      <button
        v-if="hasMore"
        class="directory-action directory-more"
        type="button"
        :disabled="loading"
        @click="$emit('more')"
      >
        加载更早会话
      </button>
    </nav>
    <div class="sidebar-bottom">
      <RouterLink
        v-if="auth.can('model:manage')"
        class="model-management-link"
        to="/models"
        active-class="is-active"
        aria-label="模型管理"
        ><SlidersHorizontal :size="17" /><span v-if="!compact">模型管理</span></RouterLink
      >
      <RouterLink
        v-if="canManageOrganization(auth.user)"
        class="model-management-link"
        to="/organization"
        active-class="is-active"
        aria-label="组织与权限"
        ><Users :size="17" /><span v-if="!compact">组织与权限</span></RouterLink
      >
      <div v-if="!compact" class="workspace-note">
        <span class="workspace-note-dot" />为每一个好想法，找到方向。
      </div>
      <ThemeMenu :compact="compact" />
      <button
        v-if="auth.user"
        class="logout-button"
        type="button"
        aria-label="退出登录"
        @click="auth.logout"
      >
        <LogOut :size="17" /><span v-if="!compact">退出登录</span>
      </button>
      <RouterLink v-if="isDev && !compact" class="preview-link" to="/dev/ui"
        >组件预览<ArrowUpRight :size="14"
      /></RouterLink>
      <div v-if="!compact" class="sidebar-profile">
        <span class="profile-avatar"><BrandLogo :size="22" /></span>
        <div>
          <span>{{ auth.user?.username ?? '知舟工作空间' }}</span
          ><small>{{ auth.user?.department?.name ?? '让工作，始于一句话' }}</small>
        </div>
        <span v-if="auth.user" class="profile-status">已登录</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.model-management-link {
  display: flex;
  align-items: center;
  gap: 9px;
  border-radius: 8px;
  padding: 10px 12px;
  text-decoration: none;
  color: var(--text-secondary);
  font-size: 13px;
}
.model-management-link:hover {
  color: var(--brand);
  background: var(--surface-hover);
}
.model-management-link.is-active {
  color: var(--brand);
  background: var(--surface-active);
}
.directory-action {
  border: 0;
  border-radius: 6px;
  padding: 4px 6px;
  background: transparent;
  color: var(--brand);
  font: inherit;
  font-size: 12px;
}
.directory-more {
  display: block;
  margin: 12px auto;
}
.directory-hint,
.directory-error {
  margin: 12px 8px;
  font-size: 12px;
  color: var(--text-muted);
}
.directory-error {
  color: var(--danger);
}
/* 导航占满宿主高度，只有会话列表滚动，底部外观与工作空间入口始终可达。 */
.chat-sidebar {
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
  padding: 28px 18px 14px;
  background: var(--sidebar-bg);
}
.sidebar-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 36px;
  padding-inline: 8px 0;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text);
  text-align: left;
}
.brand:hover {
  color: var(--brand);
}
.brand-name {
  display: flex;
  flex-direction: column;
  font-size: 22px;
  line-height: 1.3;
  font-weight: 500;
  letter-spacing: 4px;
}
.brand-en {
  margin-top: 3px;
  font-size: 9px;
  letter-spacing: 3px;
  color: var(--accent);
  font-weight: 400;
}
.new-chat-button {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-height: 42px;
  padding: 10px 12px;
  border: 1px solid var(--border-strong);
  border-radius: 30px;
  background: transparent;
  color: var(--text);
  font-size: 13px;
  font-weight: 500;
}
.new-chat-button:hover {
  background: var(--surface-hover);
}
.new-chat-button svg {
  color: var(--brand);
}
.new-chat-plus {
  margin-left: auto;
  color: var(--text-muted);
  font-size: 17px;
  font-weight: 400;
}
.conversation-nav {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  margin-top: 34px;
  scrollbar-width: thin;
}
.sidebar-section-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
  padding: 0 10px;
  color: var(--text-secondary);
  font-size: 12px;
}
.sidebar-section-label > span {
  font-size: 10px;
  color: var(--text-muted);
}
.conversation-group {
  margin-top: 20px;
}
.conversation-group h2 {
  margin: 0 10px 7px;
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 400;
}
.sidebar-bottom {
  flex-shrink: 0;
  margin-top: auto;
  padding-top: 20px;
}
.logout-button {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  min-height: 36px;
  padding: 7px 10px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  font: inherit;
  font-size: 12px;
  text-align: left;
}
.logout-button:hover {
  background: var(--surface-hover);
  color: var(--text);
}
.workspace-note {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 12px 8px 19px;
  font-size: 11px;
  color: var(--text-muted);
}
.workspace-note-dot {
  width: 5px;
  height: 5px;
  background: var(--accent);
  border-radius: 50%;
  opacity: 0.7;
}
.preview-link {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 7px 10px;
  border-radius: var(--radius-sm);
  text-decoration: none;
  font-size: 12px;
  color: var(--text-muted);
}
.preview-link:hover {
  background: var(--surface-hover);
  color: var(--text);
}
.sidebar-profile {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-top: 14px;
  padding: 16px 6px 4px;
  border-top: 1px solid var(--border);
}
.profile-avatar {
  display: grid;
  flex-shrink: 0;
  place-items: center;
  width: 33px;
  height: 33px;
  border-radius: 50%;
  background: var(--brand-soft);
  color: var(--brand);
  font-size: 14px;
}
.sidebar-profile > div {
  display: flex;
  flex-direction: column;
  font-size: 12px;
  min-width: 0;
}
.sidebar-profile > div > span,
.sidebar-profile small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sidebar-profile small {
  color: var(--text-muted);
  font-size: 10px;
}
.profile-status {
  flex-shrink: 0;
  white-space: nowrap;
  margin-left: auto;
  color: var(--text-muted);
  font-size: 8px;
  letter-spacing: 1px;
}
.is-compact {
  align-items: center;
  gap: 12px;
  padding-inline: 10px;
}
.is-compact .sidebar-heading {
  padding: 0;
  margin-bottom: 10px;
}
.is-compact .sidebar-bottom {
  padding-bottom: 12px;
}
</style>
