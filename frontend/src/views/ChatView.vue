<!-- 聊天页内容：组合首页输入、消息历史和发送区；导航与品牌外壳由 WorkspaceLayout 统一提供。 -->
<script setup lang="ts">
import UiFeedback from '@/shared/components/ui/UiFeedback.vue'
import UiButton from '@/shared/components/ui/UiButton.vue'
import { nextTick, onBeforeUnmount, ref } from 'vue'
import UiConfirmDialog from '@/shared/components/ui/UiConfirmDialog.vue'
import { storeToRefs } from 'pinia'
import { useChatStore } from '@/features/chat/store'
import ChatModelSelector from '@/features/model-selection/components/ChatModelSelector.vue'
import ChatReasoningControl from '@/features/model-selection/components/ChatReasoningControl.vue'
import ChatWelcome from '@/features/chat/components/ChatWelcome.vue'
import ChatComposer from '@/features/chat/components/ChatComposer.vue'
import MessageList from '@/features/chat/components/MessageList.vue'
const chat = useChatStore()
const { draft } = storeToRefs(chat)
const composer = ref<InstanceType<typeof ChatComposer> | InstanceType<typeof ChatWelcome>>()
// 离开聊天页撤销待确认发送，返回时由用户重新发起。
onBeforeUnmount(() => chat.cancelModelChange())
/** 发起发送或模型变化确认；仅实际发送时恢复输入焦点，让确认弹窗保持键盘焦点。 */
async function send(text: string): Promise<void> {
  if (!chat.selectionReady) return
  void chat.send(text)
  await nextTick()
  if (!chat.modelChangeConfirmation) composer.value?.focus()
}
</script>
<template>
  <div v-if="!chat.activeConversation" class="home-scroll">
    <ChatWelcome
      ref="composer"
      v-model="draft"
      :sending="chat.isSending"
      :send-blocked="!chat.selectionReady"
      @send="send"
      ><template #reasoning-controls><ChatReasoningControl /></template
      ><template #model-selector><ChatModelSelector /></template
    ></ChatWelcome>
  </div>
  <template v-else>
    <section class="conversation-scroll" aria-label="对话内容">
      <div class="history-controls">
        <UiButton
          v-if="chat.activeConversation.nextCursor"
          size="sm"
          :disabled="chat.activeConversation.loading || chat.isSending"
          @click="chat.loadEarlier"
        >
          加载更早消息
        </UiButton>
        <span v-if="chat.activeConversation.loading" role="status">正在加载历史…</span>
      </div>
      <UiFeedback
        v-if="chat.activeConversation.historyError"
        :message="chat.activeConversation.historyError"
        retry-label="重试"
        :busy="chat.activeConversation.loading"
        @retry="chat.refreshHistory"
      />
      <p v-if="chat.activeConversation.remoteRunning" class="history-notice" role="status">
        此会话正在其他页面生成，完成后将自动同步。
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
          :send-blocked="!chat.selectionReady"
          @send="send"
          ><template #reasoning-controls><ChatReasoningControl /></template
          ><template #model-selector><ChatModelSelector /></template
        ></ChatComposer>
        <p class="composer-disclaimer">AI 回复仅供参考，请核实重要信息。</p>
      </div>
    </footer>
  </template>
  <UiConfirmDialog
    v-if="chat.modelChangeConfirmation"
    :open="true"
    title="使用新模型继续对话？"
    :description="`此对话上次使用 ${chat.modelChangeConfirmation.from.display_name}，本次将使用 ${chat.modelChangeConfirmation.to.display_name}。是否继续发送？`"
    confirm-label="使用新模型发送"
    cancel-label="取消发送"
    :danger="false"
    @update:open="chat.cancelModelChange()"
    @confirm="chat.confirmModelChange()"
  />
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
.conversation-scroll > .ui-feedback {
  max-width: var(--content-width);
  margin: 12px auto;
}
.history-notice {
  max-width: var(--content-width);
  margin: 12px auto;
  font-size: 13px;
  color: var(--text-secondary);
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
  max-width: 860px;
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
