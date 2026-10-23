<!-- 青蓝水墨聊天工作空间：复用正式会话 store 与 Reka 导航，首页品牌视觉与消息阅读区独立布局。 -->
<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { PanelLeft, SquarePen } from '@lucide/vue'
import { useChatStore } from '@/stores/chat'
import { useMediaQuery } from '@/composables/useMediaQuery'
import { useMotionPreference } from '@/composables/useMotionPreference'
import ChatSidebar from '@/components/chat/ChatSidebar.vue'
import ChatWelcome from '@/components/chat/ChatWelcome.vue'
import RiverBackdrop from '@/components/chat/RiverBackdrop.vue'
import ChatComposer from '@/components/chat/ChatComposer.vue'
import MessageList from '@/components/chat/MessageList.vue'
import UiDrawer from '@/components/ui/UiDrawer.vue'
import UiIconButton from '@/components/ui/UiIconButton.vue'
import UiTooltip from '@/components/ui/UiTooltip.vue'
const chat = useChatStore()
const narrow = useMediaQuery('(max-width: 760px)')
const { enabled, visible } = useMotionPreference()
const collapsed = ref(false)
const drawerOpen = ref(false)
const draft = ref('')
const composer = ref<InstanceType<typeof ChatComposer> | InstanceType<typeof ChatWelcome>>()
const headerTitle = ref<HTMLElement>()
// 切换或删除当前会话时清空草稿；仅绑定服务端 ID 时对象不变，不打断等待中的新草稿。
watch(
  () => chat.activeConversation,
  () => {
    draft.value = ''
  },
)
// 目录在身份恢复后的工作区挂载时加载，开发组件预览不会触发真实会话请求。
onMounted(() => {
  if (!chat.listInitialized) void chat.loadConversations()
})
// 断点回到桌面后移除模态内容，交给 Reka 释放焦点约束与背景滚动锁。
watch(narrow, (value) => {
  if (!value) drawerOpen.value = false
})
/** 新建或选择会话时清空草稿并关闭抽屉，防止跨会话误发。 */
function navigate(id?: string): void {
  if (id) void chat.select(id)
  else chat.startNew()
  draft.value = ''
  drawerOpen.value = false
}
/** 提交聊天输入并将焦点移回当前输入区；后台请求由 store 管理，不等待整轮生成结束。 */
async function send(text: string): Promise<void> {
  void chat.send(text)
  await nextTick()
  composer.value?.focus()
}
/**
 * 在侧栏抽屉关闭时恢复合适的键盘焦点。
 * 窄屏关闭交给 Reka 回到触发器；若已切到桌面布局，阻止默认恢复，
 * 等待 DOM 更新后聚焦仍存在的页头，避免引用已卸载的抽屉入口。
 */
async function restoreFocus(event: Event): Promise<void> {
  if (!narrow.value) {
    event.preventDefault()
    await nextTick()
    headerTitle.value?.focus()
  }
}
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
        :active-id="chat.activeId"
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
    <main class="chat-main" :class="{ 'is-home': !chat.activeConversation }">
      <RiverBackdrop v-if="!chat.activeConversation" :motion="enabled" />
      <header class="chat-header">
        <div class="header-start">
          <UiDrawer
            v-if="narrow"
            v-model:open="drawerOpen"
            title="会话导航"
            description="新建对话、浏览会话记录或切换外观。"
            @close-auto-focus="restoreFocus"
            ><template #trigger
              ><UiIconButton label="打开侧栏"><PanelLeft :size="20" /></UiIconButton></template
            ><ChatSidebar
              :conversations="chat.conversations"
              :active-id="chat.activeId"
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
          /></UiDrawer>
          <h1 ref="headerTitle" tabindex="-1" class="header-title">
            {{ chat.activeConversation?.title ?? '此刻，思考启程' }}
          </h1>
        </div>
        <div class="header-end">
          <span class="header-edition">KNOWLEDGE IN FLOW</span
          ><span class="prototype-badge"><span />知舟 AI</span
          ><UiTooltip v-if="chat.activeConversation" text="新建对话"
            ><UiIconButton label="新建对话" @click="navigate()"
              ><SquarePen :size="18" /></UiIconButton
          ></UiTooltip>
        </div>
      </header>
      <div v-if="!chat.activeConversation" class="home-scroll">
        <ChatWelcome ref="composer" v-model="draft" :sending="chat.isSending" @send="send" />
      </div>
      <template v-else
        ><section class="conversation-scroll" aria-label="对话内容">
          <div class="history-controls">
            <button
              v-if="chat.activeConversation.nextCursor"
              type="button"
              :disabled="chat.activeConversation.loading || chat.isSending"
              @click="chat.loadEarlier"
            >
              加载更早消息
            </button>
            <button
              v-if="chat.activeConversation.persisted"
              type="button"
              :disabled="chat.activeConversation.loading || chat.isSending"
              @click="chat.refreshHistory"
            >
              刷新会话
            </button>
            <span v-if="chat.activeConversation.loading" role="status">正在加载历史…</span>
          </div>
          <p v-if="chat.activeConversation.historyError" class="history-error" role="alert">
            {{ chat.activeConversation.historyError }}
          </p>
          <p v-if="chat.activeConversation.remoteRunning" class="history-notice" role="status">
            此会话正在其他页面生成，刷新会话后查看最新结果。
          </p>
          <MessageList
            :messages="chat.activeConversation.messages"
            :conversation-id="chat.activeConversation.id"
          />
        </section>
        <footer class="conversation-footer">
          <div class="composer-container">
            <ChatComposer
              ref="composer"
              v-model="draft"
              :sending="chat.isSending"
              :disabled="chat.inputBlocked"
              @send="send"
            />
            <p class="composer-disclaimer">AI 回复仅供参考，请核实重要信息。</p>
          </div>
        </footer></template
      >
    </main>
  </div>
</template>
<style scoped>
.history-controls {
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  max-width: var(--content-width);
  margin: 0 auto 18px;
  color: var(--text-muted);
  font-size: 12px;
}
.history-controls button {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 5px 10px;
  background: var(--surface);
  color: var(--brand);
}
.history-error,
.history-notice {
  max-width: var(--content-width);
  margin: 12px auto;
  font-size: 13px;
  color: var(--text-secondary);
}
.history-error {
  color: var(--danger);
}
/* 视口只约束工作空间外壳，内容区独立滚动，底部输入区始终参与布局。 */
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
.home-scroll {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden auto;
}
.conversation-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 12px 36px 0;
  scrollbar-gutter: stable;
}
.conversation-footer {
  flex-shrink: 0;
  padding: 16px 36px 14px;
  background: var(--bg);
  border-top: 1px solid var(--border);
}
.composer-container {
  max-width: var(--content-width);
  margin: 0 auto;
}
.composer-disclaimer {
  margin: 10px 0 0;
  text-align: center;
  font-size: 11px;
  color: var(--text-muted);
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
  .conversation-scroll,
  .conversation-footer {
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
  }
  .prototype-badge {
    white-space: nowrap;
  }
  .conversation-scroll {
    padding-inline: 20px;
  }
  .conversation-footer {
    padding: 10px 16px max(12px, env(safe-area-inset-bottom));
  }
  .composer-disclaimer {
    font-size: 10px;
  }
}
</style>
