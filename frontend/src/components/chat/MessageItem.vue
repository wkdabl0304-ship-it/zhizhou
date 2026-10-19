<!-- 消息展示：助手正文解析 Markdown，用户正文保持纯文本；兼容流式状态和预览结构化块。 -->
<script setup lang="ts">
import { ref } from 'vue'
import { Check, Copy, TriangleAlert } from '@lucide/vue'
import type { ChatMessage } from '@/types/chat'
import UiIconButton from '@/components/ui/UiIconButton.vue'
import UiTooltip from '@/components/ui/UiTooltip.vue'
import BrandLogo from '@/components/BrandLogo.vue'
import MarkdownContent from './MarkdownContent.vue'

const props = defineProps<{ message: ChatMessage }>()
const copyState = ref<'idle' | 'copied' | 'failed'>('idle')

/** 复制原始消息文本（助手保留 Markdown 标记）；权限拒绝时给出可见提示。 */
async function copy(): Promise<void> {
  const text = props.message.blocks
    .map((block) =>
      block.type === 'list' ? block.items.map((item) => `- ${item}`).join('\n') : block.text,
    )
    .join('\n\n')
  try {
    await navigator.clipboard.writeText(text)
    copyState.value = 'copied'
  } catch {
    copyState.value = 'failed'
  }
}
</script>

<template>
  <article
    class="message"
    :class="`message--${message.role}`"
    :aria-label="message.role === 'user' ? '你的消息' : '知舟的回复'"
  >
    <div v-if="message.role === 'assistant'" class="assistant-heading">
      <BrandLogo :size="25" /><span>知舟</span
      ><span v-if="message.demo" class="demo-label">演示回复</span>
    </div>
    <!-- 失败时保留已接收的部分回复，并在正文下方明确提示未完成。 -->
    <div v-if="message.blocks.length" class="message-body">
      <template v-for="(block, index) in message.blocks" :key="index">
        <MarkdownContent
          v-if="block.type === 'paragraph' && message.role === 'assistant'"
          :source="block.text"
        />
        <p v-else-if="block.type === 'paragraph'">{{ block.text }}</p>
        <ul v-else-if="block.type === 'list'">
          <li v-for="(item, itemIndex) in block.items" :key="itemIndex">{{ item }}</li>
        </ul>
        <div v-else class="code-block">
          <div class="code-heading">{{ block.language }}</div>
          <pre><code>{{ block.text }}</code></pre>
        </div>
      </template>
    </div>
    <div
      v-if="message.status === 'pending' || message.status === 'streaming'"
      class="message-pending"
      role="status"
    >
      <span class="thinking-dots" aria-hidden="true"><i /><i /><i /></span>
      {{ message.status === 'streaming' ? '正在回复…' : '正在整理思路…' }}
    </div>
    <div v-if="message.status === 'error'" class="message-error" role="alert">
      <TriangleAlert :size="18" />
      <div>
        {{ message.blocks.length ? '回复未完成' : '暂时无法获取回复' }}
        <p>请稍后再试，你输入的内容{{ message.blocks.length ? '和已接收的回复' : '' }}仍然保留。</p>
      </div>
    </div>
    <div
      v-if="message.role === 'assistant' && (!message.status || message.status === 'complete')"
      class="message-actions"
    >
      <UiTooltip :text="copyState === 'copied' ? '已复制' : '复制回复'"
        ><UiIconButton :label="copyState === 'copied' ? '已复制回复' : '复制回复'" @click="copy"
          ><Check v-if="copyState === 'copied'" :size="15" /><Copy
            v-else
            :size="15" /></UiIconButton
      ></UiTooltip>
      <span class="copy-status" role="status">{{
        copyState === 'failed'
          ? '复制失败，请手动选择文本复制'
          : copyState === 'copied'
            ? '已复制'
            : ''
      }}</span>
    </div>
  </article>
</template>

<style scoped>
/* 外壳只负责消息布局；助手 Markdown 的排版与高亮由独立组件管理。 */
.message {
  min-width: 0;
  margin-bottom: 36px;
}
.message--user {
  display: flex;
  justify-content: flex-end;
  margin: 16px 0 34px;
}
.message--user .message-body {
  max-width: 85%;
  padding: 10px 18px;
  border-radius: 20px 20px 5px 20px;
  background: var(--surface-soft);
}
.message-body {
  min-width: 0;
  overflow-wrap: anywhere;
}
.message-body > .markdown-content + .markdown-content {
  margin-top: 17px;
}
.message-body p {
  margin: 0 0 17px;
  white-space: pre-wrap;
}
.message-body p:last-child {
  margin-bottom: 0;
}
.message-body ul {
  padding-left: 24px;
  margin: -4px 0 22px;
}
.message-body li {
  margin-bottom: 6px;
  padding-left: 3px;
}
.message-body li::marker {
  color: var(--text-muted);
}
.assistant-heading {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 17px;
  font-size: 13px;
  font-weight: 500;
}
.demo-label {
  margin-left: 2px;
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--surface-soft);
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 400;
}
.message-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 12px 0 0 -7px;
}
.copy-status {
  font-size: 11px;
  color: var(--text-muted);
}
.code-block {
  overflow: hidden;
  margin: 18px 0;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-soft);
}
.code-heading {
  padding: 8px 16px;
  border-bottom: 1px solid var(--border);
  color: var(--text-secondary);
  font-size: 12px;
}
pre {
  max-width: 100%;
  overflow-x: auto;
  margin: 0;
  padding: 16px;
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.7;
  tab-size: 2;
}
.message-pending {
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--text-secondary);
  font-size: 14px;
}
.thinking-dots {
  display: inline-flex;
  gap: 4px;
}
.thinking-dots i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--brand);
  animation: pulse 1.3s ease-in-out infinite;
}
.thinking-dots i:nth-child(2) {
  animation-delay: 0.15s;
}
.thinking-dots i:nth-child(3) {
  animation-delay: 0.3s;
}
.message-error {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 14px;
  border-radius: var(--radius-md);
  background: var(--danger-soft);
  color: var(--danger);
  font-size: 14px;
}
.message-error svg {
  margin-top: 4px;
}
.message-error p {
  margin: 2px 0 0;
  font-size: 12px;
}
@keyframes pulse {
  0%,
  80%,
  100% {
    opacity: 0.35;
  }
  40% {
    opacity: 1;
  }
}
@media (max-width: 760px) {
  .message--user .message-body {
    max-width: 92%;
  }
}
</style>
