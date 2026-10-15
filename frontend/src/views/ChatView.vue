<!-- 青蓝水墨聊天工作空间：复用正式会话 store 与 Reka 导航，首页品牌视觉与消息阅读区独立布局。 -->
<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { PanelLeft, SquarePen } from '@lucide/vue'
import { useChatStore } from '@/stores/chat'
import { useMediaQuery } from '@/composables/useMediaQuery'
import { useMotionPreference } from '@/composables/useMotionPreference'
import ChatSidebar from '@/components/chat/ChatSidebar.vue'
import ChatWelcome from '@/components/chat/ChatWelcome.vue'
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
// 断点回到桌面后移除模态内容，交给 Reka 释放焦点约束与背景滚动锁。
watch(narrow, (value) => {
  if (!value) drawerOpen.value = false
})
/** 新建或选择会话时清空草稿并关闭抽屉，防止跨会话误发。 */
function navigate(id?: string): void {
  if (id) chat.select(id)
  else chat.startNew()
  draft.value = ''
  drawerOpen.value = false
}
/** 发送仍使用本地固定回复，视图切换后聚焦新的输入实例。 */
async function send(text: string): Promise<void> {
  chat.send(text)
  await nextTick()
  composer.value?.focus()
}
/** 窄屏正常关闭由 Reka 恢复触发器焦点，跨断点卸载则聚焦仍存在的页头。 */
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
        @new="navigate()"
        @select="navigate"
        @toggle="collapsed = !collapsed"
      />
    </aside>
    <main class="chat-main">
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
              @new="navigate()"
              @select="navigate"
          /></UiDrawer>
          <h1 ref="headerTitle" tabindex="-1" class="header-title">
            {{ chat.activeConversation?.title ?? '此刻，思考启程' }}
          </h1>
        </div>
        <div class="header-end">
          <span class="header-edition">KNOWLEDGE IN FLOW</span
          ><span class="prototype-badge"><span />交互原型</span
          ><UiTooltip v-if="chat.activeConversation" text="新建对话"
            ><UiIconButton label="新建对话" @click="navigate()"
              ><SquarePen :size="18" /></UiIconButton
          ></UiTooltip>
        </div>
      </header>
      <div v-if="!chat.activeConversation" class="home-scroll">
        <ChatWelcome ref="composer" v-model="draft" :motion="enabled" @send="send" />
      </div>
      <template v-else
        ><section class="conversation-scroll" aria-label="对话内容">
          <MessageList
            :messages="chat.activeConversation.messages"
            :conversation-id="chat.activeConversation.id"
          />
        </section>
        <footer class="conversation-footer">
          <div class="composer-container">
            <ChatComposer ref="composer" v-model="draft" @send="send" />
            <p class="composer-disclaimer">当前为静态演示，回复不由 AI 生成。刷新后会话将重置。</p>
          </div>
        </footer></template
      >
    </main>
  </div>
</template>
<style scoped>
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
.chat-shell[data-visible='false'] :deep(*) {
  animation-play-state: paused !important;
}
.chat-shell[data-motion='off'] :deep(*) {
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
