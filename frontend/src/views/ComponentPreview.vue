<!-- 开发组件预览：验证主题、浮层、长文本与消息状态；路由仅在 Vite 开发环境注册。 -->
<script setup lang="ts">
import { ref } from 'vue'
import { ArrowLeft, PanelLeft, Plus, Search, Mail } from '@lucide/vue'
import { DropdownMenuItem } from 'reka-ui'
import ThemeMenu from '@/shared/components/ThemeMenu.vue'
import UiButton from '@/shared/components/ui/UiButton.vue'
import UiTag from '@/shared/components/ui/UiTag.vue'
import UiFeedback from '@/shared/components/ui/UiFeedback.vue'
import UiPageHeader from '@/shared/components/ui/UiPageHeader.vue'
import UiModal from '@/shared/components/ui/UiModal.vue'
import UiConfirmDialog from '@/shared/components/ui/UiConfirmDialog.vue'
import UiDialogActions from '@/shared/components/ui/UiDialogActions.vue'
import UiIconButton from '@/shared/components/ui/UiIconButton.vue'
import UiTooltip from '@/shared/components/ui/UiTooltip.vue'
import UiDrawer from '@/shared/components/ui/UiDrawer.vue'
import UiDropdownMenu from '@/shared/components/ui/UiDropdownMenu.vue'
import UiInput from '@/shared/components/ui/UiInput.vue'
import UiSelect from '@/shared/components/ui/UiSelect.vue'
import UiCheckbox from '@/shared/components/ui/UiCheckbox.vue'
import UiSwitch from '@/shared/components/ui/UiSwitch.vue'
import UiAutoTextarea from '@/shared/components/ui/UiAutoTextarea.vue'
import ChatComposer from '@/features/chat/components/ChatComposer.vue'
import MessageItem from '@/features/chat/components/MessageItem.vue'
import type { ChatMessage } from '@/features/chat/types'

const exampleModal = ref(false),
  exampleConfirm = ref(false)
const draft = ref('')
const exampleFailure = ref(true)
const drawer = ref(false)
const submitted = ref('')
const menuSelection = ref('尚未选择')
const fieldExample = ref(''),
  selectedState = ref(''),
  onlyUnassigned = ref(false),
  notifications = ref(true),
  notes = ref(''),
  formResult = ref('')
const stateOptions = [
  { value: '', label: '全部状态' },
  { value: 'active', label: '已启用' },
  { value: 'inactive', label: '已停用' },
  { value: 'archived', label: '已归档 · 暂不可选', disabled: true },
]
// 同文案、同语义色对照留白差异，避免误把颜色或字号变化当成尺寸效果。
const tagSizes = [
  { size: 'xs', label: 'XS · 行内身份' },
  { size: 'sm', label: 'SM · 普通列表' },
  { size: 'md', label: 'MD · 独立状态' },
  { size: 'lg', label: 'LG · 重点展示' },
] as const

/** 显示共享控件当前结果，便于验证输入、选择与复选是否在同一表单中协作。 */
function submitControls(): void {
  const label = stateOptions.find((option) => option.value === selectedState.value)?.label
  formResult.value = `${fieldExample.value || '未填写用户名'} · ${label} · ${onlyUnassigned.value ? '仅无部门' : '不限部门'}`
}
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
        '使用服务端签发的 `conversation_id` 关联对话。代码块支持独立复制：',
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

// 过程样例完全使用本地数据；命令卡片只演示协议 kind=command，不实际执行系统命令。
const processMessage: ChatMessage = {
  id: 'process',
  role: 'assistant',
  demo: true,
  status: 'complete',
  blocks: [
    {
      type: 'paragraph',
      text: '**处理完成。** 可展开查看本轮行动说明、工具参数与执行结果。',
    },
  ],
  activities: [
    {
      type: 'text',
      id: 'progress-plan',
      messageId: 'plan',
      text: '我先查询上海的天气。',
      status: 'complete',
    },
    {
      type: 'tool',
      id: 'weather',
      toolCallId: 'weather',
      name: 'get_weather',
      kind: 'tool',
      status: 'complete',
      runs: [
        {
          runId: 'weather-run',
          kind: 'tool',
          status: 'complete',
          arguments: { city: '上海' },
          output: '上海今天晴天，温度 25°C',
        },
      ],
    },
    {
      type: 'text',
      id: 'next-step',
      messageId: 'next-step',
      text: '天气结果已返回，我接着检查项目目录。',
      status: 'complete',
    },
    {
      type: 'tool',
      id: 'command',
      toolCallId: 'command',
      name: 'project_command',
      kind: 'command',
      status: 'complete',
      runs: [
        {
          runId: 'command-run',
          kind: 'command',
          status: 'complete',
          arguments: { command: 'pwd' },
          output: '/workspace/zhizhou',
        },
      ],
    },
    {
      type: 'tool',
      id: 'rejected',
      toolCallId: 'rejected',
      name: 'unavailable_tool',
      kind: 'tool',
      status: 'error',
      error: '工具不可用，请稍后重试',
      runs: [],
    },
  ],
}

// 保持等待的样例用于验证动画、折叠交互与长参数滚动，不创建真实在途请求。
const runningProcessMessage: ChatMessage = {
  id: 'process-running',
  role: 'assistant',
  demo: true,
  status: 'streaming',
  blocks: [],
  activities: [
    {
      type: 'text',
      id: 'running-preface',
      messageId: 'running-preface',
      text: '我先运行构建，检查当前项目是否可以正常打包。',
      status: 'complete',
    },
    {
      type: 'tool',
      id: 'running-command',
      toolCallId: 'running-command',
      name: 'project_command',
      kind: 'command',
      status: 'running',
      runs: [
        {
          runId: 'running',
          kind: 'command',
          status: 'running',
          arguments: { command: 'pnpm build' },
        },
      ],
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
    <UiPageHeader
      title="组件与交互预览"
      eyebrow="ZHIZHOU · DESIGN FOUNDATION"
      description="开发专用 · 所有示例都使用演示数据。通过外观菜单检查明暗主题。"
      size="lg"
    />
    <section>
      <h2>基础操作</h2>
      <div class="preview-row">
        <UiButton variant="primary">主要操作</UiButton><UiButton>次要操作</UiButton
        ><UiButton variant="ghost">轻量操作</UiButton><UiButton disabled>禁用操作</UiButton
        ><UiButton variant="danger">删除操作</UiButton><UiButton loading>处理中</UiButton
        ><UiTooltip text="支持键盘聚焦与 Esc 关闭"
          ><UiIconButton label="示例提示"><Plus :size="18" /></UiIconButton
        ></UiTooltip>
      </div>
    </section>
    <section aria-label="标签与失败反馈">
      <h2>标签与失败反馈</h2>
      <div class="preview-row">
        <UiTag size="xs">普通用户</UiTag><UiTag size="xs" tone="brand">本人</UiTag
        ><UiTag size="xs" tone="accent">超级管理员</UiTag> <UiTag tone="brand" dot>已启用</UiTag
        ><UiTag dot>已停用</UiTag><UiTag tone="danger" dot>不可用</UiTag>
        <UiTag size="xs" tone="brand">当前默认</UiTag>
      </div>
      <p class="preview-status">
        尺寸主要调整内边距与间距；姓名旁和密集目录用 XS，独立状态可用 MD 或 LG。
      </p>
      <div class="preview-tag-sizes" role="group" aria-label="标签尺寸对比">
        <div v-for="example in tagSizes" :key="example.size" class="preview-tag-size">
          <span>{{ example.label }}</span>
          <UiTag :size="example.size" tone="brand" dot>已启用</UiTag>
        </div>
      </div>
      <UiFeedback
        v-if="exampleFailure"
        title="暂时无法读取目录"
        message="网络连接中断，请检查网络后重试。"
        retry-label="重试示例"
        @retry="exampleFailure = false"
      />
      <UiButton v-else size="sm" @click="exampleFailure = true">再次模拟失败</UiButton>
      <UiFeedback compact message="请输入完整的邮箱地址。" />
    </section>
    <section aria-label="基础表单控件">
      <div class="preview-section-heading">
        <div>
          <h2>基础表单控件</h2>
          <p class="preview-status">
            输入、选择与勾选共用纸面、细边框和柔和焦点，保留原生表单语义。
          </p>
        </div>
        <UiTag tone="accent">FORM CONTROLS</UiTag>
      </div>
      <form class="preview-controls" aria-label="控件联动示例" @submit.prevent="submitControls">
        <label class="preview-field" for="preview-username"
          >用户名<UiInput
            id="preview-username"
            v-model="fieldExample"
            name="preview_username"
            aria-label="示例用户名"
            placeholder="输入一个用户名"
            ><template #prefix><Search :size="16" /></template></UiInput
          ><small>输入框支持图标、数字、密码及原生输入属性。</small></label
        >
        <label class="preview-field" for="preview-state"
          >账号状态<UiSelect
            id="preview-state"
            v-model="selectedState"
            name="preview_state"
            :options="stateOptions"
            aria-label="示例账号状态"
          /><small>方向键浏览，Enter 确认，Esc 取消。</small></label
        >
        <div class="preview-checks">
          <UiCheckbox v-model="onlyUnassigned">仅无部门</UiCheckbox
          ><UiCheckbox :model-value="true" disabled>已选中 · 不可修改</UiCheckbox
          ><UiSwitch v-model="notifications" label="接收通知" />
        </div>
        <div class="preview-row">
          <UiButton type="submit" variant="primary">查看表单结果</UiButton
          ><span class="preview-status" role="status">{{
            formResult || '改变上方选项后查看结果。'
          }}</span>
        </div>
      </form>
      <div class="preview-state-grid">
        <label class="preview-field"
          >错误状态<UiInput
            model-value="invalid@example"
            type="email"
            aria-invalid="true"
            aria-describedby="preview-input-error"
            ><template #prefix><Mail :size="16" /></template></UiInput
          ><UiFeedback id="preview-input-error" compact message="请输入完整的邮箱地址。" />
        </label>
        <label class="preview-field">禁用输入<UiInput model-value="当前不可编辑" disabled /></label>
        <label class="preview-field">只读输入<UiInput model-value="已确认的信息" readonly /></label>
        <label class="preview-field"
          >禁用选择<UiSelect model-value="active" :options="stateOptions" disabled
        /></label>
        <label class="preview-field">紧凑尺寸<UiInput placeholder="搜索或筛选" size="sm" /></label>
        <label class="preview-field"
          >错误选择<UiSelect
            :options="stateOptions.slice(1)"
            placeholder="请选择一项"
            aria-invalid="true"
            size="sm"
        /></label>
      </div>
      <label class="preview-field preview-notes"
        >自适应文本域
        <div class="preview-textarea">
          <UiAutoTextarea
            v-model="notes"
            label="示例备注"
            placeholder="写下几句备注，内容增加时自动展开…"
          /></div
      ></label>
    </section>
    <section>
      <h2>公共弹窗与确认</h2>
      <div class="preview-row">
        <UiButton @click="exampleModal = true">打开内容弹窗</UiButton
        ><UiButton variant="danger" @click="exampleConfirm = true">打开确认弹窗</UiButton>
      </div>
      <UiModal
        v-if="exampleModal"
        :open="true"
        title="公共内容弹窗"
        description="内容、底栏与关闭行为可以独立配置。"
        size="md"
        @update:open="exampleModal = false"
        ><p>使用同一套主题、焦点约束及明暗配色。</p>
        <template #footer
          ><UiDialogActions
            confirm-label="完成"
            @cancel="exampleModal = false"
            @confirm="exampleModal = false" /></template
      ></UiModal>
      <UiConfirmDialog
        v-if="exampleConfirm"
        :open="true"
        title="确认执行示例操作？"
        description="此示例不会调用接口或删除任何数据。"
        confirm-label="确认操作"
        @update:open="exampleConfirm = false"
        @confirm="exampleConfirm = false"
      />
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
            ? `演示内容：${submitted}`
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
      <h2>进度正文、工具与命令过程</h2>
      <MessageItem :message="processMessage" />
      <MessageItem :message="runningProcessMessage" />
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
.preview-tag-sizes {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 16px;
  margin-block: 18px;
}
.preview-tag-size {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}
.preview-tag-size > span {
  color: var(--text-muted);
  font-size: 11px;
}
.preview-disabled {
  margin-top: 24px;
}
.preview-drawer-content {
  padding: 72px 24px 24px;
}
.preview-section-heading {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 16px;
}
.preview-section-heading h2 {
  margin-bottom: 8px;
}
.preview-controls,
.preview-state-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 22px;
  margin-top: 24px;
}
.preview-field {
  display: grid;
  align-content: start;
  gap: 8px;
  min-width: 0;
  color: var(--text-secondary);
  font-size: 13px;
}
.preview-field small {
  font-size: 11px;
  color: var(--text-muted);
}
.preview-field .preview-error {
  color: var(--danger);
}
.preview-checks,
.preview-controls > .preview-row {
  grid-column: 1 / -1;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 24px;
}
.preview-state-grid {
  padding-top: 24px;
  border-top: 1px dashed var(--border);
}
.preview-notes {
  margin-top: 24px;
}
.preview-textarea {
  padding: 12px 14px;
  border: 1px solid var(--border-strong);
  border-radius: 10px;
  background: var(--surface);
}
.preview-textarea:focus-within {
  border-color: var(--brand);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--brand) 12%, transparent);
}
@media (max-width: 760px) {
  .preview-page {
    padding-inline: 20px;
  }
  .preview-controls,
  .preview-state-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .preview-component-tag {
    display: none;
  }
}
</style>
