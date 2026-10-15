<!-- 聊天侧栏：共用于桌面导航与窄屏抽屉，向上报告选择、新建和折叠事件。 -->
<script setup lang="ts">
import { computed } from 'vue'
import { ArrowUpRight, PanelLeft, SquarePen } from '@lucide/vue'
import type { Conversation } from '@/types/chat'
import ThemeMenu from '@/components/ThemeMenu.vue'
import BrandLogo from '@/components/BrandLogo.vue'
import UiIconButton from '@/components/ui/UiIconButton.vue'
import UiTooltip from '@/components/ui/UiTooltip.vue'
import ConversationItem from './ConversationItem.vue'

const props = defineProps<{
  conversations: Conversation[]
  activeId: string | null
  compact?: boolean
  drawer?: boolean
}>()
defineEmits<{ select: [id: string]; new: []; toggle: [] }>()
const isDev = import.meta.env.DEV
// 根据演示会话自身分组，新增会话自动进入“今天”。
const groups = computed(() => [...new Set(props.conversations.map((item) => item.group))])
</script>

<template>
  <div class="chat-sidebar" :class="{ 'is-compact': compact }">
    <div class="sidebar-heading">
      <div class="brand" :class="{ 'brand--compact': compact }">
        <BrandLogo :size="compact ? 34 : 39" /><span v-if="!compact" class="brand-name"
          >知舟<span class="brand-en">ZHIZHOU</span></span
        >
      </div>
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
      <div class="sidebar-section-label">你的对话<span>仅本次浏览</span></div>
      <section v-for="group in groups" :key="group" class="conversation-group" :aria-label="group">
        <h2>{{ group }}</h2>
        <template v-for="conversation in conversations" :key="conversation.id"
          ><ConversationItem
            v-if="conversation.group === group"
            :title="conversation.title"
            :active="conversation.id === activeId"
            @select="$emit('select', conversation.id)"
        /></template>
      </section>
    </nav>
    <div class="sidebar-bottom">
      <div v-if="!compact" class="workspace-note">
        <span class="workspace-note-dot" />为每一个好想法，找到方向。
      </div>
      <ThemeMenu :compact="compact" />
      <RouterLink v-if="isDev && !compact" class="preview-link" to="/dev/ui"
        >组件预览<ArrowUpRight :size="14"
      /></RouterLink>
      <div v-if="!compact" class="sidebar-profile">
        <span class="profile-avatar"><BrandLogo :size="22" /></span>
        <div><span>知舟工作空间</span><small>让工作，始于一句话</small></div>
        <span class="profile-status" aria-label="演示模式">DEMO</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
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
  color: var(--text-muted);
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
  background: var(--brand);
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
}
.sidebar-profile small {
  color: var(--text-muted);
  font-size: 10px;
}
.profile-status {
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
