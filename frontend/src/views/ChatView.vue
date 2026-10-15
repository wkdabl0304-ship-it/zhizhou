<!-- 聊天工作空间：组合公共组件与内存会话，桌面侧栏和窄屏 Dialog 互斥挂载。 -->
<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { ArrowUpRight, CheckCheck, Lightbulb, NotebookPen, PanelLeft, SquarePen } from '@lucide/vue'
import { useChatStore } from '@/stores/chat'
import { useMediaQuery } from '@/composables/useMediaQuery'
import { suggestions } from '@/data/demo'
import ChatSidebar from '@/components/chat/ChatSidebar.vue'
import ChatComposer from '@/components/chat/ChatComposer.vue'
import MessageList from '@/components/chat/MessageList.vue'
import UiDrawer from '@/components/ui/UiDrawer.vue'
import UiIconButton from '@/components/ui/UiIconButton.vue'
import UiTooltip from '@/components/ui/UiTooltip.vue'

const chat = useChatStore()
const narrow = useMediaQuery('(max-width: 760px)')
const collapsed = ref(false)
const drawerOpen = ref(false)
const draft = ref('')
const composer = ref<InstanceType<typeof ChatComposer>>()
const headerTitle = ref<HTMLElement>()

// 切换到桌面时立即关闭并卸载 Dialog，释放焦点约束与背景滚动锁。
watch(narrow, (value) => {
  if (!value) drawerOpen.value = false
})

/** 新建或选择会话时清除未发送草稿，关闭抽屉，防止跨会话误发内容。 */
function navigate(id?: string): void {
  if (id) chat.select(id)
  else chat.startNew()
  draft.value = ''
  drawerOpen.value = false
}

/** 填入示例内容并聚焦输入框；不自动发送，用户仍可编辑。 */
async function fillSuggestion(prompt: string): Promise<void> {
  draft.value = prompt
  await nextTick()
  composer.value?.focus()
}

/** 将草稿交给演示 store；网络接口留待下一阶段接入。 */
async function send(text: string): Promise<void> {
  chat.send(text)
  // 首页与对话页使用不同输入区实例；等待切换完成后重新聚焦，支持连续输入。
  await nextTick()
  composer.value?.focus()
}

/** 窄屏关闭恢复触发器；断点卸载后改为聚焦仍存在的页头，避免焦点落到 body。 */
async function restoreFocus(event: Event): Promise<void> {
  if (!narrow.value) {
    event.preventDefault()
    await nextTick()
    headerTitle.value?.focus()
  }
}
</script>

<template>
  <div class="chat-shell" :class="{ 'sidebar-collapsed': collapsed }">
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
          >
            <template #trigger
              ><UiIconButton label="打开侧栏"><PanelLeft :size="20" /></UiIconButton
            ></template>
            <ChatSidebar
              :conversations="chat.conversations"
              :active-id="chat.activeId"
              drawer
              @new="navigate()"
              @select="navigate"
            />
          </UiDrawer>
          <h1 ref="headerTitle" tabindex="-1" class="header-title">
            {{ chat.activeConversation?.title ?? '新的开始' }}
          </h1>
        </div>
        <div class="header-end">
          <span class="prototype-badge"><span />交互原型</span
          ><UiTooltip v-if="chat.activeConversation" text="新建对话"
            ><UiIconButton label="新建对话" @click="navigate()"
              ><SquarePen :size="18" /></UiIconButton
          ></UiTooltip>
        </div>
      </header>
      <div v-if="!chat.activeConversation" class="home-scroll">
        <section class="welcome" aria-label="开启新对话">
          <div class="welcome-eyebrow">
            <span class="welcome-line" /><span>让想法，有处启航</span>
          </div>
          <h2>你好，<span>今天想从哪里开始？</span></h2>
          <p class="welcome-subtitle">
            梳理思路、准备工作，或是探索一个新想法。<br
              class="mobile-break"
            />知舟，陪你一起往前一步。
          </p>
          <ChatComposer ref="composer" v-model="draft" @send="send" />
          <div class="suggestions-label">不妨从这些开始</div>
          <div class="suggestions">
            <button
              v-for="suggestion in suggestions"
              :key="suggestion.title"
              type="button"
              class="suggestion"
              @click="fillSuggestion(suggestion.prompt)"
            >
              <span class="suggestion-icon"
                ><CheckCheck v-if="suggestion.icon === 'checklist'" :size="19" /><NotebookPen
                  v-else-if="suggestion.icon === 'report'"
                  :size="19" /><Lightbulb v-else :size="19"
              /></span>
              <span class="suggestion-title">{{ suggestion.title }}<ArrowUpRight :size="15" /></span
              ><span class="suggestion-description">{{ suggestion.description }}</span>
            </button>
          </div>
        </section>
        <div class="home-watermark" aria-hidden="true"><span />知识有岸，探索无界<span /></div>
      </div>
      <template v-else>
        <section class="conversation-scroll" aria-label="对话内容">
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
        </footer>
      </template>
      <footer v-if="!chat.activeConversation" class="home-footer">
        静态演示 · 不连接 AI 服务 · 会话仅在本次浏览中保留
      </footer>
    </main>
  </div>
</template>

<style scoped>
/* 工作空间锁定视口高度，各内容区独立滚动，输入区始终参与布局而非覆盖消息。 */
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
  border-right: 1px solid var(--border);
  background: var(--sidebar-bg);
}
.chat-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}
.chat-header {
  z-index: var(--z-header);
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 72px;
  padding: 16px 32px;
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
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
}
.header-title:focus {
  outline: none;
}
.prototype-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 9px;
  border: 1px solid var(--border);
  border-radius: 20px;
  color: var(--text-muted);
  font-size: 11px;
}
.prototype-badge > span {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--brand);
}
.home-scroll {
  position: relative;
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  overflow-y: auto;
  padding: 0 36px;
}
.welcome {
  width: min(100%, var(--content-width));
  margin: auto;
  padding: 54px 0 72px;
}
.welcome-eyebrow {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 20px;
  color: var(--brand);
  font-size: 12px;
  letter-spacing: 2px;
}
.welcome-line {
  width: 23px;
  height: 2px;
  background: var(--brand);
}
.welcome h2 {
  margin: 0 0 13px;
  font-size: clamp(26px, 2.6vw, 36px);
  line-height: 1.5;
  font-weight: 500;
  letter-spacing: -0.8px;
}
.welcome h2 span {
  color: var(--text-secondary);
}
.welcome-subtitle {
  margin: 0 0 34px;
  color: var(--text-muted);
  font-size: 14px;
}
.mobile-break {
  display: none;
}
.suggestions-label {
  margin: 30px 0 12px;
  font-size: 12px;
  color: var(--text-muted);
}
.suggestions {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.suggestion {
  display: flex;
  min-width: 0;
  flex-direction: column;
  align-items: flex-start;
  padding: 18px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg);
  text-align: left;
  transition:
    background var(--duration-fast),
    border-color var(--duration-fast);
}
.suggestion:hover {
  background: var(--surface-soft);
  border-color: var(--border-strong);
}
.suggestion-icon {
  display: inline-flex;
  margin-bottom: 17px;
  color: var(--brand);
}
.suggestion-title {
  display: flex;
  width: 100%;
  justify-content: space-between;
  align-items: center;
  gap: 4px;
  font-size: 14px;
  font-weight: 500;
}
.suggestion-title svg {
  color: var(--text-muted);
}
.suggestion-description {
  margin-top: 5px;
  color: var(--text-muted);
  font-size: 12px;
}
.home-watermark {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 15px;
  padding-bottom: 26px;
  font-size: 11px;
  color: var(--text-muted);
  letter-spacing: 3px;
}
.home-watermark span {
  width: 30px;
  height: 1px;
  background: var(--border);
}
.home-footer {
  flex-shrink: 0;
  padding: 12px 24px 18px;
  text-align: center;
  font-size: 11px;
  color: var(--text-muted);
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
@media (min-width: 1600px) {
  .welcome {
    padding-bottom: 100px;
  }
}
@media (max-width: 1024px) {
  .chat-header {
    padding-inline: 24px;
  }
  .home-scroll,
  .conversation-scroll {
    padding-inline: 24px;
  }
  .suggestion {
    padding: 14px;
  }
  .conversation-footer {
    padding-inline: 24px;
  }
}
@media (max-width: 760px) {
  .chat-shell,
  .chat-shell.sidebar-collapsed {
    grid-template-columns: minmax(0, 1fr);
  }
  .chat-header {
    min-height: 64px;
    padding: 12px 16px;
  }
  .header-start {
    gap: 8px;
  }
  .prototype-badge {
    font-size: 10px;
    padding: 3px 7px;
    white-space: nowrap;
  }
  .home-scroll {
    padding-inline: 24px;
  }
  .welcome {
    padding: 38px 0;
  }
  .welcome h2 {
    font-size: 27px;
    letter-spacing: -0.6px;
  }
  .welcome h2 span {
    display: block;
  }
  .welcome-subtitle {
    margin-bottom: 26px;
    font-size: 13px;
  }
  .mobile-break {
    display: block;
  }
  .suggestions {
    grid-template-columns: 1fr;
    gap: 8px;
  }
  .suggestion {
    position: relative;
    min-height: 66px;
    padding: 10px 14px 10px 48px;
  }
  .suggestion-icon {
    position: absolute;
    left: 16px;
    top: 18px;
    margin: 0;
  }
  .suggestion-description {
    margin-top: 1px;
  }
  .suggestions-label {
    margin-top: 24px;
  }
  .home-watermark {
    display: none;
  }
  .home-footer {
    padding: 10px 16px max(14px, env(safe-area-inset-bottom));
    font-size: 10px;
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
