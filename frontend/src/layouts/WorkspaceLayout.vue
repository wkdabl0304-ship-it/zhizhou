<!-- 登录工作区共用布局：聊天与模型管理保留同一侧栏、折叠状态和移动抽屉，子页面只维护内容。 -->
<script setup lang="ts">
import UiFeedback from '@/shared/components/ui/UiFeedback.vue'
import UiTag from '@/shared/components/ui/UiTag.vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PanelLeft, SquarePen } from '@lucide/vue'
import { useChatStore } from '@/features/chat/store'
import ChatSidebar from '@/features/chat/components/ChatSidebar.vue'
import ConversationDialogs from '@/features/chat/components/ConversationDialogs.vue'
import type { ConversationDialogRequest } from '@/features/chat/types'
import UiPageHeader from '@/shared/components/ui/UiPageHeader.vue'
import RiverBackdrop from '@/shared/components/RiverBackdrop.vue'
import { useMediaQuery } from '@/shared/composables/useMediaQuery'
import { useMotionPreference } from '@/shared/composables/useMotionPreference'
import UiDrawer from '@/shared/components/ui/UiDrawer.vue'
import UiIconButton from '@/shared/components/ui/UiIconButton.vue'
import UiTooltip from '@/shared/components/ui/UiTooltip.vue'
import { useAuthStore } from '@/features/auth/store'

const route = useRoute(),
  router = useRouter(),
  chat = useChatStore()
const auth = useAuthStore()
const checkingIdentity = ref(false)

/** 在临时断网后重新确认当前授权，失败继续保持管理入口关闭，成功恢复可用导航。 */
async function retryIdentity(): Promise<void> {
  if (checkingIdentity.value) return
  checkingIdentity.value = true
  try {
    await auth.refreshIdentity()
    if (!auth.restoreError) auth.notice = ''
  } finally {
    checkingIdentity.value = false
  }
}
const narrow = useMediaQuery('(max-width: 760px)')
const { enabled, visible } = useMotionPreference()
const collapsed = ref(false),
  drawerOpen = ref(false),
  headerTitle = ref<InstanceType<typeof UiPageHeader>>()
const actionRequest = ref<ConversationDialogRequest | null>(null)
const management = computed(() => route.name === 'models' || route.name === 'organization')
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
  if (id === chat.activeId && route.name === 'chat') {
    drawerOpen.value = false
    return
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
    if (headerTitle.value) headerTitle.value.focus()
    else document.querySelector<HTMLElement>('main h1[tabindex]')?.focus()
  }
}
/** 固定会话操作目标和触发器，导航、标题双击与按钮都共用一个弹窗宿主。 */
function openAction(kind: 'rename' | 'delete', id: string, trigger: HTMLElement | null): void {
  const row = chat.conversations.find((item) => item.id === id)
  if (!row?.persisted || row.deleting || row.titleSaving || (kind === 'delete' && row.running))
    return
  actionRequest.value = { id, kind, trigger }
}
/** 双击聊天页标题改名，键盘用户仍可从侧栏铅笔按钮进入。 */
function renameActive(event: MouseEvent): void {
  if (chat.activeId) openAction('rename', chat.activeId, event.currentTarget as HTMLElement)
}
/** 工作区重新可见时同步目录和已保存历史，保留草稿且不覆盖本地生成中的消息。 */
function synchronize(): void {
  if (document.hidden) return
  void chat.loadConversations()
  if (route.name === 'chat' && chat.activeConversation?.persisted && !chat.isSending)
    void chat.refreshHistory()
}
// 远端生成没有本页流连接，仅为当前可见会话轮询，离页或结束时释放定时器。
watch(
  () => [route.name, chat.activeId, chat.activeConversation?.remoteRunning],
  (_, __, cleanup) => {
    if (route.name !== 'chat' || !chat.activeConversation?.remoteRunning) return
    const timer = setInterval(() => {
      if (!document.hidden && !chat.isSending) void chat.refreshHistory()
    }, 2000)
    cleanup(() => clearInterval(timer))
  },
)
// 导航只随工作区初始化，跨子页面保留目录、折叠状态及侧栏的滚动位置。
onMounted(() => {
  if (!chat.listInitialized) void chat.loadConversations()
  window.addEventListener('focus', synchronize)
  document.addEventListener('visibilitychange', synchronize)
})
onBeforeUnmount(() => {
  window.removeEventListener('focus', synchronize)
  document.removeEventListener('visibilitychange', synchronize)
})
watch(narrow, (value) => {
  if (!value) drawerOpen.value = false
})
// 页面导航完成后释放抽屉焦点约束及滚动锁；取消导航则不关闭当前抽屉。
watch(
  () => route.fullPath,
  () => {
    drawerOpen.value = false
    actionRequest.value = null
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
        renamable
        @retry="chat.loadConversations()"
        @more="chat.loadConversations(true)"
        @delete="(id, trigger) => openAction('delete', id, trigger)"
        @rename="(id, trigger) => openAction('rename', id, trigger)"
        @new="navigate()"
        @select="navigate"
        @toggle="collapsed = !collapsed"
      />
    </aside>
    <main class="chat-main" :class="{ 'is-home': home, 'is-management': management }">
      <UiFeedback
        v-if="auth.restoreError"
        :message="auth.restoreError + '；管理操作已暂停。'"
        retry-label="重试权限校验"
        :busy="checkingIdentity"
        @retry="retryIdentity"
      />
      <UiFeedback v-else-if="auth.notice" :message="auth.notice" />
      <RiverBackdrop v-if="home" :motion="enabled" />
      <UiPageHeader
        v-if="!management"
        ref="headerTitle"
        class="chat-header"
        :title="title"
        size="sm"
        truncate
        :editable="!!chat.activeConversation?.persisted"
        @title-dblclick="renameActive"
      >
        <template #actions
          ><div class="header-end">
            <span class="header-edition">KNOWLEDGE IN FLOW</span
            ><UiTag size="sm" tone="brand" dot>知舟 AI</UiTag
            ><UiTooltip v-if="!management && chat.activeConversation" text="新建对话"
              ><UiIconButton label="新建对话" @click="navigate()"
                ><SquarePen :size="18" /></UiIconButton
            ></UiTooltip></div
        ></template>
      </UiPageHeader>
      <RouterView v-slot="{ Component, route: childRoute }"
        ><component :is="Component" :key="childRoute.name ?? childRoute.path"
      /></RouterView>
      <ConversationDialogs
        v-if="actionRequest"
        :key="actionRequest.kind + actionRequest.id"
        :request="actionRequest"
        :nested="drawerOpen"
        @close="actionRequest = null"
      />
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
            renamable
            @retry="chat.loadConversations()"
            @more="chat.loadConversations(true)"
            @delete="(id, trigger) => openAction('delete', id, trigger)"
            @rename="(id, trigger) => openAction('rename', id, trigger)"
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
.chat-main > .ui-feedback {
  flex-shrink: 0;
  margin: 12px 16px;
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
  color: var(--accent);
  font-size: 9px;
  letter-spacing: 1.5px;
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
  .chat-header {
    padding-left: 60px;
  }
  .prototype-badge {
    white-space: nowrap;
  }
}
</style>
