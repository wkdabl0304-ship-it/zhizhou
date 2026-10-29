<!-- 共享富文本组件：随源文更新 Markdown，并通过事件委托复制各代码块的原始文本。 -->
<script setup lang="ts">
import UiFeedback from './ui/UiFeedback.vue'
import { computed, ref } from 'vue'
import { renderMarkdown } from '@/shared/utils/markdown'

const props = defineProps<{ source: string }>()
// 将最新 Markdown 源文渲染为展示 HTML，流式增量到达后自动重新计算。
const html = computed(() => renderMarkdown(props.source))
const copyFeedback = ref('')

/**
 * 复制用户点击的 Markdown 代码块，并显示成功或失败反馈。
 * event 由正文容器委托，仅处理本组件内的代码复制按钮；读取 textContent，
 * 避免把语法高亮标签写入剪贴板，权限或浏览器限制失败时提示手动复制。
 */
async function copyCode(event: MouseEvent): Promise<void> {
  if (!(event.target instanceof Element) || !(event.currentTarget instanceof Element)) return
  const button = event.target.closest('button.markdown-code-copy')
  if (!button || !event.currentTarget.contains(button)) return
  const code = button.closest('.markdown-code')?.querySelector('pre code')
  if (!code) return
  try {
    await navigator.clipboard.writeText(code.textContent ?? '')
    copyFeedback.value = ''
  } catch {
    copyFeedback.value = '复制失败，请手动选择代码复制'
  }
}
</script>

<template>
  <div class="markdown-content">
    <!-- 仅注入受控解析器生成的 HTML；html:false 禁止执行助手源文中的 HTML 标签。 -->
    <div class="markdown-body" @click="copyCode" v-html="html" />
    <UiFeedback v-if="copyFeedback" compact :message="copyFeedback" />
  </div>
</template>

<style scoped>
/* v-html 的后代不带 Vue 作用域属性，样式通过 :deep 限定在本组件内部。 */
.markdown-content {
  min-width: 0;
  line-height: 1.8;
  overflow-wrap: anywhere;
}
.markdown-body :deep(> :first-child) {
  margin-top: 0;
}
.markdown-body :deep(> :last-child) {
  margin-bottom: 0;
}
.markdown-body :deep(p) {
  margin: 0 0 16px;
}
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4),
.markdown-body :deep(h5),
.markdown-body :deep(h6) {
  margin: 26px 0 12px;
  font-weight: 650;
  line-height: 1.45;
}
.markdown-body :deep(h1) {
  font-size: 1.6em;
}
.markdown-body :deep(h2) {
  font-size: 1.35em;
}
.markdown-body :deep(h3) {
  font-size: 1.15em;
}
.markdown-body :deep(h4),
.markdown-body :deep(h5),
.markdown-body :deep(h6) {
  font-size: 1em;
}
.markdown-body :deep(strong) {
  font-weight: 700;
}
.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 0 0 16px;
  padding-left: 26px;
}
.markdown-body :deep(li) {
  margin: 5px 0;
  padding-left: 3px;
}
.markdown-body :deep(li > p) {
  margin: 6px 0;
}
.markdown-body :deep(li > ul),
.markdown-body :deep(li > ol) {
  margin: 6px 0;
}
.markdown-body :deep(li::marker) {
  color: var(--text-secondary);
}
.markdown-body :deep(blockquote) {
  margin: 16px 0;
  padding: 10px 18px;
  border-left: 3px solid var(--brand);
  background: var(--surface-soft);
  color: var(--text-secondary);
}
.markdown-body :deep(blockquote > :last-child) {
  margin-bottom: 0;
}
.markdown-body :deep(a) {
  color: var(--brand);
  text-underline-offset: 3px;
}
.markdown-body :deep(hr) {
  margin: 24px 0;
  border: 0;
  border-top: 1px solid var(--border-strong);
}
.markdown-body :deep(img) {
  display: block;
  max-width: 100%;
  height: auto;
  border-radius: var(--radius-sm);
}
.markdown-body :deep(:not(pre) > code) {
  padding: 2px 5px;
  border-radius: 4px;
  background: var(--surface-soft);
  font-family: var(--font-mono);
  font-size: 0.88em;
  white-space: break-spaces;
}
.markdown-body :deep(.markdown-code) {
  margin: 18px 0;
  overflow: hidden;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-md);
  background: var(--surface-soft);
}
.markdown-body :deep(.markdown-code-heading) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 7px 14px;
  border-bottom: 1px solid var(--border);
  color: var(--text-secondary);
  font-size: 12px;
}
.markdown-body :deep(pre) {
  max-width: 100%;
  overflow-x: auto;
  margin: 0;
  padding: 16px;
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.7;
  tab-size: 2;
  white-space: pre;
  overflow-wrap: normal;
}
.markdown-body :deep(pre code) {
  font: inherit;
}
.markdown-body :deep(.markdown-table) {
  margin: 18px 0;
  overflow-x: auto;
}
.markdown-body :deep(table) {
  min-width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}
.markdown-body :deep(th),
.markdown-body :deep(td) {
  min-width: 100px;
  padding: 9px 14px;
  border: 1px solid var(--border-strong);
}
.markdown-body :deep(th) {
  background: var(--surface-soft);
  font-weight: 600;
}
.markdown-body :deep(.hljs-keyword),
.markdown-body :deep(.hljs-selector-tag),
.markdown-body :deep(.hljs-title) {
  color: var(--syntax-keyword);
}
.markdown-body :deep(.hljs-string),
.markdown-body :deep(.hljs-attr) {
  color: var(--syntax-string);
}
.markdown-body :deep(.hljs-number),
.markdown-body :deep(.hljs-literal) {
  color: var(--syntax-number);
}
.markdown-body :deep(.hljs-comment),
.markdown-body :deep(.hljs-meta) {
  color: var(--syntax-comment);
}
</style>
