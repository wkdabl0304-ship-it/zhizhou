<!-- 聊天页内容：组合首页输入、消息历史和发送区；导航与品牌外壳由 WorkspaceLayout 统一提供。 -->
<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useChatStore } from '@/features/chat/store'
import { useModelConfigStore } from '@/features/model-config/store'
import DefaultModelStatus from '@/features/model-config/components/DefaultModelStatus.vue'
import ChatWelcome from '@/features/chat/components/ChatWelcome.vue'
import ChatComposer from '@/features/chat/components/ChatComposer.vue'
import MessageList from '@/features/chat/components/MessageList.vue'
const chat = useChatStore(),
  modelConfig = useModelConfigStore()
const { draft } = storeToRefs(chat)
const composer = ref<InstanceType<typeof ChatComposer> | InstanceType<typeof ChatWelcome>>()
/** 发送消息后恢复输入焦点，服务端拒绝缺失默认时同步最新配置状态。 */
async function send(text: string): Promise<void> {
  if (!modelConfig.ready) return
  void chat.send(text).then((success) => {
    if (!success && chat.lastErrorCode === 50301) void modelConfig.loadDefault()
  })
  await nextTick()
  composer.value?.focus()
}
</script>
<template>
  <DefaultModelStatus />
  <div v-if="!chat.activeConversation" class="home-scroll">
    <ChatWelcome
      ref="composer"
      v-model="draft"
      :sending="chat.isSending"
      :send-blocked="!modelConfig.ready"
      @send="send"
    />
  </div>
  <template v-else>
    <section class="conversation-scroll" aria-label="对话内容">
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
          :send-blocked="!modelConfig.ready"
          @send="send"
        />
        <p class="composer-disclaimer">AI 回复仅供参考，请核实重要信息。</p>
      </div>
    </footer>
  </template>
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
@media (max-width: 1024px) {
  .conversation-scroll,
  .conversation-footer {
    padding-inline: 24px;
  }
}
@media (max-width: 760px) {
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
