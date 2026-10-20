<!-- Agent 时间线：正文与工具按事件顺序显示，成功后整体折叠；展开仍可查看完整过程。 -->
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check, ChevronRight, Terminal, Wrench } from '@lucide/vue'
import type { ActivityStatus, ChatActivity, ChatMessage, ToolActivity } from '@/types/chat'
import type { JsonValue } from '@/types/chat-events'
import MarkdownContent from './MarkdownContent.vue'

const props = defineProps<{ activities: ChatActivity[]; status?: ChatMessage['status'] }>()
const expanded = ref(props.status !== 'complete')

// 只在整轮状态变化时切换展开状态；工具和文本增量不覆盖用户的阅读选择。
watch(
  () => props.status,
  (status) => {
    expanded.value = status !== 'complete'
  },
)
// 汇总工具请求数而非事件数；重复执行仍归属同一操作，整轮状态控制折叠入口。
const toolCount = computed(() => props.activities.filter((item) => item.type === 'tool').length)
const finished = computed(() => props.status === 'complete' || props.status === 'error')
const statusLabels: Record<ActivityStatus, string> = {
  queued: '已请求，等待执行',
  running: '执行中',
  complete: '已完成',
  error: '失败',
  interrupted: '未确认完成',
}

/** 字符串保留换行，其他 JSON 格式化；null、false、0 都是有效结果。 */
function formatValue(value: JsonValue): string {
  return typeof value === 'string' ? value : JSON.stringify(value, null, 2)
}

/** 在工具摘要行显示实际命令或输入，未执行的请求不会被标记为正在运行。 */
function inputPreview(item: ToolActivity): string {
  const input = item.runs[item.runs.length - 1]?.arguments ?? item.arguments
  if (input === undefined) return ''
  if (typeof input === 'object' && typeof input.command === 'string') return input.command
  return typeof input === 'string' ? input : JSON.stringify(input)
}

/** 用户主动展开或收起完整过程；内容保留在 DOM 中，工具详情的展开状态不丢失。 */
function toggleProcess(): void {
  expanded.value = !expanded.value
}
</script>

<template>
  <section v-if="activities.length" class="agent-activity" aria-label="执行过程">
    <button
      v-if="finished"
      type="button"
      class="process-toggle"
      :aria-expanded="expanded"
      @click="toggleProcess"
    >
      <Check v-if="status === 'complete'" :size="15" aria-hidden="true" />
      <span
        >{{ status === 'complete' ? '已完成' : '执行中断'
        }}<template v-if="toolCount"> · {{ toolCount }} 项操作</template></span
      >
      <ChevronRight :size="15" :class="{ rotated: expanded }" aria-hidden="true" />
    </button>
    <div v-show="expanded" class="process-timeline">
      <div
        v-for="item in activities"
        :key="item.id"
        class="process-entry"
        :data-status="item.status"
      >
        <MarkdownContent v-if="item.type === 'text'" class="process-text" :source="item.text" />
        <details v-else class="tool-detail">
          <summary class="tool-summary">
            <Terminal v-if="item.kind === 'command'" :size="15" aria-hidden="true" />
            <Wrench v-else :size="15" aria-hidden="true" />
            <span class="tool-label">{{ item.kind === 'command' ? '命令执行' : '工具调用' }}</span>
            <span class="tool-name">{{ item.name }}</span>
            <code class="input-preview">{{ inputPreview(item) }}</code>
            <span class="tool-status" :class="`tool-status--${item.status}`">{{
              statusLabels[item.status]
            }}</span>
            <ChevronRight class="tool-chevron" :size="14" aria-hidden="true" />
          </summary>
          <div class="tool-content">
            <div v-if="!item.runs.length && item.arguments !== undefined" class="activity-field">
              <span>请求参数</span>
              <pre>{{ formatValue(item.arguments) }}</pre>
            </div>
            <p v-if="item.error" class="activity-error">{{ item.error }}</p>
            <section
              v-for="(run, index) in item.runs"
              :key="run.runId"
              class="tool-run"
              :data-status="run.status"
            >
              <div class="run-heading">
                <span>{{ item.runs.length > 1 ? `第 ${index + 1} 次执行` : '执行详情' }}</span>
                <span>{{ statusLabels[run.status] }}</span>
              </div>
              <div v-if="run.arguments !== undefined" class="activity-field">
                <span>{{ run.kind === 'command' ? '命令参数' : '输入参数' }}</span>
                <pre>{{ formatValue(run.arguments) }}</pre>
              </div>
              <div v-if="run.output !== undefined" class="activity-field">
                <span>{{ run.kind === 'command' ? '命令输出' : '返回结果' }}</span>
                <pre>{{ formatValue(run.output) }}</pre>
              </div>
              <p v-if="run.error" class="activity-error">{{ run.error }}</p>
              <p v-if="run.status === 'interrupted'" class="activity-note">
                未收到执行结果，当前无法确认是否完成。
              </p>
            </section>
            <p v-if="item.status === 'queued'" class="activity-note">
              调用请求已生成，尚未开始执行。
            </p>
            <p v-if="item.status === 'interrupted' && !item.runs.length" class="activity-note">
              本轮已结束，未收到执行确认。
            </p>
          </div>
        </details>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* 与助手正文共用宽度和主题；细线连接工具步骤，避免每段进度都成为独立的大卡片。 */
.agent-activity {
  min-width: 0;
  margin-bottom: 20px;
}
.process-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 0;
  border: 0;
  background: transparent;
  color: var(--text-muted);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.process-toggle:hover {
  color: var(--text);
}
.process-toggle:focus-visible,
.tool-summary:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: 4px;
}
.process-toggle svg,
.tool-chevron {
  transition: transform var(--duration-fast);
}
.rotated,
.tool-detail[open] > summary .tool-chevron {
  transform: rotate(90deg);
}
.process-toggle + .process-timeline {
  margin-top: 16px;
}
.process-timeline {
  display: grid;
  gap: 18px;
  min-width: 0;
}
.process-entry {
  min-width: 0;
}
.tool-detail {
  border-left: 2px solid var(--border);
  padding-left: 13px;
}
.tool-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  color: var(--text-secondary);
  cursor: pointer;
  list-style: none;
  font-size: 12px;
}
.tool-summary::-webkit-details-marker {
  display: none;
}
.tool-summary > svg,
.tool-label,
.tool-status {
  flex-shrink: 0;
}
.tool-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.input-preview {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-muted);
  font-size: 11px;
}
.tool-status {
  margin-left: auto;
  color: var(--text-muted);
  font-size: 11px;
}
.tool-status--running {
  color: var(--brand);
}
.tool-status--error,
.activity-error {
  color: var(--danger);
}
.tool-content {
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  background: var(--surface-soft);
  font-size: 12px;
}
.run-heading {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--text-muted);
}
.tool-run + .tool-run {
  border-top: 1px solid var(--border);
  padding-top: 12px;
  margin-top: 12px;
}
.activity-field {
  margin-top: 10px;
  color: var(--text-secondary);
}
.activity-field > span {
  color: var(--text-muted);
  font-size: 11px;
}
.activity-field pre {
  max-height: 320px;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.7;
}
.activity-note {
  color: var(--text-muted);
}
@media (max-width: 600px) {
  .tool-summary {
    flex-wrap: wrap;
  }
  .input-preview {
    order: 1;
    flex-basis: 100%;
    padding-left: 23px;
  }
  .tool-name {
    max-width: 40%;
  }
}
@media (prefers-reduced-motion: reduce) {
  .process-toggle svg,
  .tool-chevron {
    transition: none;
  }
}
</style>
