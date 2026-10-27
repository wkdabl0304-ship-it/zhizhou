<!-- 登录工作区共用布局：聊天与模型管理保留同一侧栏、折叠状态和移动抽屉，子页面只维护内容。 -->
<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PanelLeft, SquarePen } from '@lucide/vue'
import { useChatStore } from '@/features/chat/store'
import ChatSidebar from '@/features/chat/components/ChatSidebar.vue'
import RiverBackdrop from '@/features/chat/components/RiverBackdrop.vue'
import { useMediaQuery } from '@/shared/composables/useMediaQuery'
import { useMotionPreference } from '@/shared/composables/useMotionPreference'
import UiDrawer from '@/shared/components/ui/UiDrawer.vue'
import UiIconButton from '@/shared/components/ui/UiIconButton.vue'
import UiTooltip from '@/shared/components/ui/UiTooltip.vue'

const route = useRoute(),
  router = useRouter(),
  chat = useChatStore()
const narrow = useMediaQuery('(max-width: 760px)')
const { enabled, visible } = useMotionPreference()
const collapsed = ref(false),
  drawerOpen = ref(false),
  headerTitle = ref<HTMLElement>()
const management = computed(() => route.name === 'models')
const home = computed(() => !management.value && !chat.activeConversation)
const title = computed(() =>
  management.value ? '工作空间 / 模型管理' : (chat.activeConversation?.title ?? '此刻，思考启程'),
)

/** 从任一工作区页面打开会话；离页被取消时不清空草稿或更改当前会话。 */
async function navigate(id?: string): Promise<void> {
  if (route.name !== 'chat') {
    const failure = await router.push({ name: 'chat' })
    if (failure) return
  }
  if (id) void chat.select(id)
  else chat.startNew()
  chat.draft = ''
  drawerOpen.value = false
}
/** 关闭移动导航时恢复入口；切到桌面后聚焦仍存在的页头，避免引用已卸载节点。 */
async function restoreFocus(event: Event): Promise<void> {
  if (!narrow.value) {
    event.preventDefault()
    await nextTick()
    const target = headerTitle.value?.isConnected
      ? headerTitle.value
      : document.querySelector<HTMLElement>('main h1[tabindex]')
    target?.focus()
  }
}
// 导航只随工作区初始化，跨子页面保留目录、折叠状态及侧栏的滚动位置。
onMounted(() => {
  if (!chat.listInitialized) void chat.loadConversations()
})
watch(narrow, (value) => {
  if (!value) drawerOpen.value = false
})
// 页面导航完成后释放抽屉焦点约束及滚动锁；取消导航则不关闭当前抽屉。
watch(
  () => route.fullPath,
  () => {
    drawerOpen.value = false
  },
)
</script>
<template>
  <div
    class="chat-shell"
    :class="{ 'sidebar-collapsed': collapsed }"
    :data-motion="enabled ? 'on' : 'off'"
    :data-visible="visible"
  >
    <aside v-if="!narrow" class="desktop-sidebar" aria-label="知舟导航">
      <ChatSidebar
        :conversations="chat.conversations"
        :active-id="management ? null : chat.activeId"
        :compact="collapsed"
        :loading="chat.listing"
        :error="chat.listError"
        :action-error="chat.actionError"
        :has-more="Boolean(chat.nextCursor)"
        @refresh="chat.loadConversations()"
        @more="chat.loadConversations(true)"
        @delete="chat.remove"
        @new="navigate()"
        @select="navigate"
        @toggle="collapsed = !collapsed"
      />
    </aside>
    <main class="chat-main" :class="{ 'is-home': home, 'is-management': management }">
      <RiverBackdrop v-if="home" :motion="enabled" />
      <header v-if="!management" class="chat-header">
        <div class="header-start">
          <component
            :is="management ? 'p' : 'h1'"
            ref="headerTitle"
            tabindex="-1"
            class="header-title"
            >{{ title }}</component
          >
        </div>
        <div class="header-end">
          <span class="header-edition">KNOWLEDGE IN FLOW</span
          ><span class="prototype-badge"><span />知舟 AI</span
          ><UiTooltip v-if="!management && chat.activeConversation" text="新建对话"
            ><UiIconButton label="新建对话" @click="navigate()"
              ><SquarePen :size="18" /></UiIconButton
          ></UiTooltip>
        </div>
      </header>
      <RouterView v-slot="{ Component, route: childRoute }"
        ><component :is="Component" :key="childRoute.name ?? childRoute.path"
      /></RouterView>
      <!-- 手机导航独立于子页面挂载，管理页中与标题同行，切换页面不会丢失入口。 -->
      <div v-if="narrow" class="workspace-mobile-navigation">
        <UiDrawer
          v-model:open="drawerOpen"
          title="会话导航"
          description="新建对话、浏览会话记录、管理模型或切换外观。"
          @close-auto-focus="restoreFocus"
        >
          <template #trigger
            ><UiIconButton label="打开侧栏"><PanelLeft :size="20" /></UiIconButton
          ></template>
          <ChatSidebar
            :conversations="chat.conversations"
            :active-id="management ? null : chat.activeId"
            drawer
            :loading="chat.listing"
            :error="chat.listError"
            :action-error="chat.actionError"
            :has-more="Boolean(chat.nextCursor)"
            @refresh="chat.loadConversations()"
            @more="chat.loadConversations(true)"
            @delete="chat.remove"
            @new="navigate()"
            @select="navigate"
          />
        </UiDrawer>
      </div>
    </main>
  </div>
</template>
<style scoped>
.workspace-mobile-navigation {
  position: absolute;
  top: 10px;
  left: 16px;
  z-index: var(--z-header);
}
.is-management > .workspace-mobile-navigation {
  left: auto;
  right: 16px;
  top: 16px;
}
/* 保持原聊天侧栏尺寸；导航与页内滚动隔离，内容不会挤压或重新定位侧栏。 */
.chat-shell {
  display: grid;
  grid-template-columns: var(--sidebar-width) minmax(0, 1fr);
  height: 100dvh;
  overflow: hidden;
}
.chat-shell.sidebar-collapsed {
  grid-template-columns: 72px minmax(0, 1fr);
}
.desktop-sidebar {
  min-height: 0;
  border-right: 1px solid var(--border-strong);
  background: var(--sidebar-bg);
}
.chat-main {
  position: relative;
  isolation: isolate;
  display: flex;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
}
.chat-header {
  display: flex;
  z-index: var(--z-header);
  flex-shrink: 0;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 64px;
  padding: 14px 30px;
  background: var(--bg);
}
.is-home .chat-header {
  background: transparent;
}
.header-start,
.header-end {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.header-end {
  flex-shrink: 0;
}
.header-title {
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 400;
}
.header-title:focus {
  outline: none;
}
.header-edition {
  color: var(--text-muted);
  font-size: 9px;
  letter-spacing: 1.5px;
}
.prototype-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 8px;
  border: 1px solid var(--border);
  border-radius: 20px;
  color: var(--text-muted);
  font-size: 10px;
}
.prototype-badge > span {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--brand);
}
.chat-shell[data-visible='false'] :deep(*),
.chat-shell[data-visible='false'] :deep(*::before),
.chat-shell[data-visible='false'] :deep(*::after) {
  animation-play-state: paused !important;
}
.chat-shell[data-motion='off'] :deep(*),
.chat-shell[data-motion='off'] :deep(*::before),
.chat-shell[data-motion='off'] :deep(*::after) {
  animation: none !important;
  transition: none !important;
}
@media (max-width: 1024px) {
  .chat-header {
    padding-inline: 24px;
  }
  .header-edition {
    display: none;
  }
}
@media (max-width: 760px) {
  .chat-shell,
  .chat-shell.sidebar-collapsed {
    grid-template-columns: minmax(0, 1fr);
  }
  .chat-header {
    min-height: 58px;
    padding: 10px 16px;
  }
  .header-start {
    gap: 8px;
    padding-left: 44px;
  }
  .prototype-badge {
    white-space: nowrap;
  }
}
</style>
