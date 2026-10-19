<!-- Agent 过程卡片：折叠展示模型提供的思考、工具请求和命令执行，参数与输出仅按文本显示。 -->
<script setup lang="ts">
import { Brain, ChevronRight, Terminal, Wrench } from '@lucide/vue'
import type { ActivityStatus, ChatActivity } from '@/types/chat'
import type { JsonValue } from '@/types/chat-events'

defineProps<{ activities: ChatActivity[] }>()

const statusLabels: Record<ActivityStatus, string> = {
  queued: '已请求，等待执行',
  running: '执行中',
  complete: '已完成',
  error: '失败',
  interrupted: '未确认完成',
}

/** 字符串保留换行，其他 JSON 格式化缩进；null/false/0 都是有效输出，不能按真假过滤。 */
function formatValue(value: JsonValue): string {
  return typeof value === 'string' ? value : JSON.stringify(value, null, 2)
}

/** 思考状态只表示是否仍在接收文本，工具状态则来自实际执行事件。 */
function statusLabel(item: ChatActivity): string {
  if (item.type === 'reasoning') {
    return item.status === 'running' ? '思考中' : item.status === 'complete' ? '已结束' : '已中断'
  }
  return statusLabels[item.status]
}
</script>

<template>
  <section v-if="activities.length" class="agent-activity" aria-label="思考与执行过程">
    <details
      v-for="item in activities"
      :key="item.id"
      class="activity-card"
      :class="`activity-card--${item.type}`"
      :data-status="item.status"
    >
      <summary class="activity-summary">
        <Brain v-if="item.type === 'reasoning'" :size="16" aria-hidden="true" />
        <Terminal v-else-if="item.kind === 'command'" :size="16" aria-hidden="true" />
        <Wrench v-else :size="16" aria-hidden="true" />
        <span class="activity-title">{{
          item.type === 'reasoning' ? '思考过程' : item.kind === 'command' ? '命令执行' : '工具调用'
        }}</span>
        <span v-if="item.type === 'tool'" class="activity-name">{{ item.name }}</span>
        <span class="activity-status"
          ><i v-if="item.status === 'running'" aria-hidden="true" />{{ statusLabel(item) }}</span
        >
        <ChevronRight class="activity-chevron" :size="15" aria-hidden="true" />
      </summary>
      <div class="activity-content">
        <p v-if="item.type === 'reasoning'" class="reasoning-text">{{ item.text }}</p>
        <template v-else>
          <div v-if="!item.runs.length && item.arguments !== undefined" class="activity-field">
            <span class="activity-field-label">请求参数</span>
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
              <span>{{ item.runs.length > 1 ? `第 ${index + 1} 次执行` : '执行详情' }}</span
              ><span>{{ statusLabels[run.status] }}</span>
            </div>
            <div v-if="run.arguments !== undefined" class="activity-field">
              <span class="activity-field-label">{{
                run.kind === 'command' ? '命令参数' : '输入参数'
              }}</span>
              <pre>{{ formatValue(run.arguments) }}</pre>
            </div>
            <div v-if="run.output !== undefined" class="activity-field">
              <span class="activity-field-label">{{
                run.kind === 'command' ? '命令输出' : '返回结果'
              }}</span>
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
        </template>
      </div>
    </details>
  </section>
</template>

<style scoped>
/* 卡片默认折叠，原生 details 保留用户展开选择，流式更新不强制改变阅读位置。 */
.agent-activity {
  display: grid;
  gap: 8px;
  min-width: 0;
  margin: 0 0 20px;
}
.activity-card {
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
}
.activity-summary {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
  padding: 10px 12px;
  cursor: pointer;
  list-style: none;
  color: var(--text-secondary);
  font-size: 12px;
}
.activity-summary::-webkit-details-marker {
  display: none;
}
.activity-title {
  flex-shrink: 0;
  font-weight: 500;
}
.activity-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--font-mono);
}
.activity-status {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  gap: 6px;
  margin-left: auto;
  color: var(--text-muted);
  font-size: 11px;
}
.activity-status i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--brand);
  animation: activity-pulse 1.4s ease-in-out infinite;
}
.activity-chevron {
  flex-shrink: 0;
  transition: transform var(--duration-fast);
}
.activity-card[open] .activity-chevron {
  transform: rotate(90deg);
}
.activity-card[data-status='error'] .activity-status,
.activity-error {
  color: var(--danger);
}
.activity-card[data-status='running'] .activity-status {
  color: var(--brand);
}
.activity-content {
  min-width: 0;
  padding: 2px 14px 14px;
  border-top: 1px solid var(--border);
}
.reasoning-text {
  margin: 12px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.85;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.activity-field {
  min-width: 0;
  margin-top: 12px;
}
.activity-field-label {
  color: var(--text-muted);
  font-size: 11px;
}
.activity-field pre {
  max-height: 320px;
  overflow: auto;
  margin: 6px 0 0;
  padding: 12px;
  border-radius: 6px;
  background: var(--surface-soft);
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.run-heading {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-top: 12px;
  color: var(--text-secondary);
  font-size: 11px;
}
.tool-run + .tool-run {
  margin-top: 14px;
  padding-top: 4px;
  border-top: 1px solid var(--border);
}
.activity-error,
.activity-note {
  margin: 10px 0 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-size: 12px;
}
.activity-note {
  color: var(--text-muted);
}
@keyframes activity-pulse {
  50% {
    opacity: 0.35;
  }
}
@media (prefers-reduced-motion: reduce) {
  .activity-status i {
    animation: none;
  }
}
@media (max-width: 480px) {
  .activity-summary {
    flex-wrap: wrap;
    gap: 7px;
  }
  .activity-name {
    flex: 1;
  }
}
</style>
