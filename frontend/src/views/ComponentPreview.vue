<!-- 开发组件预览：验证主题、浮层、长文本与消息状态；路由仅在 Vite 开发环境注册。 -->
<script setup lang="ts">
import { ref } from 'vue'
import { ArrowLeft, PanelLeft, Plus } from '@lucide/vue'
import { DropdownMenuItem } from 'reka-ui'
import ThemeMenu from '@/components/ThemeMenu.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiIconButton from '@/components/ui/UiIconButton.vue'
import UiTooltip from '@/components/ui/UiTooltip.vue'
import UiDrawer from '@/components/ui/UiDrawer.vue'
import UiDropdownMenu from '@/components/ui/UiDropdownMenu.vue'
import ChatComposer from '@/components/chat/ChatComposer.vue'
import MessageItem from '@/components/chat/MessageItem.vue'
import type { ChatMessage } from '@/types/chat'

const draft = ref('')
const drawer = ref(false)
const submitted = ref('')
const menuSelection = ref('尚未选择')
const longMessage: ChatMessage = {
  id: 'long',
  role: 'assistant',
  demo: true,
  blocks: [
    {
      type: 'paragraph',
      text: '这是一段用于检查中文阅读体验的示例。段落需要有足够的呼吸感，长文本也应自然换行，保持清晰的阅读节奏。'.repeat(
        4,
      ),
    },
    {
      type: 'list',
      items: [
        '列表与段落使用统一的正文尺寸。',
        '超长连续内容不会撑宽页面：' + 'abcdefghijklmnopqrstuvwxyz'.repeat(6),
      ],
    },
    {
      type: 'code',
      language: '文本示例',
      text:
        '这段内容作为纯文本呈现，不执行 HTML。\n<img src="x" onerror="alert(1)" />\n' +
        'example_'.repeat(30),
    },
  ],
}

// 用真实 Markdown 展示助手回复排版，供明暗主题和窄屏下人工检查，不调用模型。
const richMessage: ChatMessage = {
  id: 'markdown',
  role: 'assistant',
  demo: true,
  blocks: [
    {
      type: 'paragraph',
      text: [
        '## 把想法变成行动',
        '',
        '**先明确目标**，再把任务拆成*可验证的小步骤*。',
        '',
        '> 清晰的下一步，比一份冗长的计划更容易开始。',
        '',
        '1. 确认本周目标',
        '2. 安排一次简短同步',
        '   - 记录风险',
        '   - 约定负责人',
        '',
        '| 任务 | 负责人 | 状态 |',
        '| --- | --- | --- |',
        '| 整理需求 | 项目团队 | **进行中** |',
        '',
        '使用 `thread_id` 关联对话。代码块支持独立复制：',
        '',
        '```python',
        'def greet(name):',
        '    return f"你好，{name}"',
        '```',
        '',
        '[查看 Markdown 语法](https://commonmark.org/help/)',
      ].join('\n'),
    },
  ],
}

/** 记录输入结果作为可见反馈，原型不请求后端或外部模型。 */
function record(text: string): void {
  submitted.value = text
}
</script>

<template>
  <main class="preview-page">
    <header class="preview-header">
      <RouterLink to="/" class="back-link"><ArrowLeft :size="17" />返回知舟</RouterLink
      ><ThemeMenu />
    </header>
    <div class="preview-eyebrow">ZHIZHOU · DESIGN FOUNDATION</div>
    <h1>组件与交互预览</h1>
    <p class="preview-intro">开发专用 · 所有示例都使用演示数据。通过外观菜单检查明暗主题。</p>
    <section>
      <h2>基础操作</h2>
      <div class="preview-row">
        <UiButton variant="primary">主要操作</UiButton><UiButton>次要操作</UiButton
        ><UiButton variant="ghost">轻量操作</UiButton><UiButton disabled>禁用操作</UiButton
        ><UiButton loading>处理中</UiButton
        ><UiTooltip text="支持键盘聚焦与 Esc 关闭"
          ><UiIconButton label="示例提示"><Plus :size="18" /></UiIconButton
        ></UiTooltip>
      </div>
    </section>
    <section>
      <h2>菜单与抽屉</h2>
      <div class="preview-row">
        <UiDropdownMenu
          ><template #trigger><UiButton>打开示例菜单</UiButton></template
          ><DropdownMenuItem class="ui-menu-item" @select="menuSelection = '已选择第一个操作'"
            >第一个操作</DropdownMenuItem
          ><DropdownMenuItem class="ui-menu-item" @select="menuSelection = '已选择第二个操作'"
            >第二个操作</DropdownMenuItem
          ><DropdownMenuItem class="ui-menu-item" disabled
            >不可用操作</DropdownMenuItem
          ></UiDropdownMenu
        ><UiDrawer
          v-model:open="drawer"
          title="抽屉示例"
          description="用于检查焦点约束、Esc 关闭与焦点恢复。"
          ><template #trigger
            ><UiButton><PanelLeft :size="16" />打开抽屉</UiButton></template
          >
          <div class="preview-drawer-content">
            <h2>抽屉示例</h2>
            <p>使用 Tab 在抽屉内移动，按 Esc 返回触发按钮。</p>
            <UiButton @click="drawer = false">完成</UiButton>
          </div></UiDrawer
        ><span class="preview-status" role="status">{{ menuSelection }}</span>
      </div>
    </section>
    <section>
      <h2>输入区</h2>
      <ChatComposer v-model="draft" @send="record" />
      <p class="preview-status" role="status">
        {{
          submitted
            ? `已发送演示内容：${submitted}`
            : 'Enter 发送 · Shift+Enter 换行 · 中文输入法确认不发送'
        }}
      </p>
      <div class="preview-disabled"><ChatComposer model-value="输入区暂不可用" disabled /></div>
    </section>
    <section>
      <h2>等待与失败</h2>
      <MessageItem
        :message="{ id: 'pending', role: 'assistant', status: 'pending', blocks: [] }"
      /><MessageItem :message="{ id: 'error', role: 'assistant', status: 'error', blocks: [] }" />
    </section>
    <section>
      <h2>Markdown 富文本回复</h2>
      <MessageItem :message="richMessage" />
    </section>
    <section>
      <h2>长文本、列表与代码</h2>
      <MessageItem :message="longMessage" />
    </section>
  </main>
</template>

<style scoped>
.preview-page {
  max-width: 920px;
  margin: 0 auto;
  padding: 24px 32px 64px;
}
.preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 64px;
}
.preview-header > :last-child {
  max-width: 150px;
}
.back-link {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  text-decoration: none;
  font-size: 14px;
}
.preview-eyebrow {
  font-size: 11px;
  letter-spacing: 2px;
  color: var(--brand);
}
h1 {
  margin: 10px 0;
  font-size: 30px;
  font-weight: 500;
}
.preview-intro {
  font-size: 14px;
  color: var(--text-secondary);
}
section {
  margin-top: 40px;
  padding-top: 24px;
  border-top: 1px solid var(--border);
}
h2 {
  margin: 0 0 20px;
  font-size: 16px;
  font-weight: 500;
}
.preview-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}
.preview-status {
  color: var(--text-muted);
  font-size: 12px;
  overflow-wrap: anywhere;
}
.preview-disabled {
  margin-top: 24px;
}
.preview-drawer-content {
  padding: 72px 24px 24px;
}
@media (max-width: 760px) {
  .preview-page {
    padding-inline: 20px;
  }
}
</style>
