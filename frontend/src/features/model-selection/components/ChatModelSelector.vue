<!-- 输入区模型下拉：以单个入口选择模型，推理、错误恢复和管理入口收进浮层，沿用会话选择版本。 -->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { PopoverRoot, PopoverTrigger, PopoverPortal, PopoverContent } from 'reka-ui'
import { ChevronDown, Check, AlertCircle } from '@lucide/vue'
import { useChatStore } from '@/features/chat/store'
import { modeLabels } from '@/features/model-config/validation'
import { useModelSelectionStore } from '../store'
import { decodeSelection, validateSelection } from '../contract'
import type { ConcreteReasoning, ModelSelection } from '../types'
const chat = useChatStore(),
  choices = useModelSelectionStore()
const open = ref(false)
const draft = ref<ModelSelection | null>(null),
  error = ref('')
const model = computed(() =>
  choices.models.find(
    (model) => model.model_configuration_id === draft.value?.model_configuration_id,
  ),
)
const confirmed = computed(() =>
  choices.models.find(
    (model) => model.model_configuration_id === chat.effectiveSelection?.model_configuration_id,
  ),
)
const locked = computed(
  () => chat.isSending || chat.inputBlocked || !!chat.activeConversation?.selectionSaving,
)
/** 恢复当前已确认选择，不把编辑中的未保存预算带到另一个会话。 */
function reset(): void {
  chat.selectionEditing = false
  draft.value = chat.effectiveSelection ? decodeSelection(chat.effectiveSelection) : null
  error.value = ''
}
// 会话切换时关闭当前浮层，避免把未确认参数带入另一会话。
watch(
  () => chat.activeId,
  () => {
    open.value = false
    reset()
  },
  { immediate: true },
)
watch(
  () => chat.effectiveSelection,
  () => {
    if (!chat.selectionEditing) reset()
  },
  { deep: true },
)
/** 显式提交完整具体值；失败保留当前控件草稿，绝不自动重发聊天。 */
async function apply(): Promise<boolean> {
  if (!draft.value || !model.value || locked.value) return false
  if (model.value.reasoning_control.mode === 'fixed')
    draft.value.reasoning = { ...model.value.reasoning_control.default }
  error.value = validateSelection(draft.value, model.value)
  if (error.value) return false
  const target = chat.activeId
  if ((await chat.chooseSelection(decodeSelection(draft.value))) && chat.activeId === target) {
    reset()
    return true
  }
  return false
}
/** 更换方案时复制其具体默认，已有会话立即保存，不能修改选项缓存。 */
async function changeModel(id: string): Promise<void> {
  const next = choices.models.find((model) => model.model_configuration_id === id)
  if (!next || locked.value || choices.loading) return
  draft.value = { model_configuration_id: id, reasoning: { ...next.reasoning_control.default } }
  chat.selectionEditing = true
  if (await apply()) setOpen(false)
}
/** 更换推理方式时只创建该分支参数，取值顺序沿用后端范围。 */
async function changeMode(event: Event): Promise<void> {
  const control = model.value?.reasoning_control,
    mode = (event.target as HTMLSelectElement).value as ConcreteReasoning['mode']
  if (!draft.value || control?.mode !== 'selectable' || !control.allowed_modes.includes(mode))
    return
  draft.value.reasoning =
    mode === 'off'
      ? { mode }
      : mode === 'effort'
        ? {
            mode,
            effort:
              control.default.mode === 'effort'
                ? control.default.effort
                : control.effort_options[0]!,
          }
        : {
            mode,
            budget_tokens:
              control.default.mode === 'budget'
                ? control.default.budget_tokens
                : control.budget!.min,
          }
  chat.selectionEditing = true
  await apply()
}
/** 档位选择立即保存；不按名称推测其他模型的等级或排序。 */
async function changeEffort(event: Event): Promise<void> {
  if (!draft.value) return
  draft.value.reasoning = { mode: 'effort', effort: (event.target as HTMLSelectElement).value }
  chat.selectionEditing = true
  await apply()
}
/** 预算输入只更新控件草稿，明确确认有效整数后才向服务端写入。 */
function changeBudget(event: Event): void {
  if (!draft.value) return
  draft.value.reasoning = {
    mode: 'budget',
    budget_tokens: (event.target as HTMLInputElement).valueAsNumber,
  }
  chat.selectionEditing = true
}
/** 关闭浮层时放弃未确认输入，发送仍使用服务端已确认的具体选择。 */
function setOpen(value: boolean): void {
  open.value = value
  if (!value) reset()
}
/** 在模型列表中移动键盘焦点，只有 Enter 或空格明确选择时才保存。 */
function navigateModels(event: KeyboardEvent): void {
  if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return
  const list = event.currentTarget as HTMLElement
  const buttons = [...list.querySelectorAll<HTMLButtonElement>('[role="option"]:not(:disabled)')]
  if (!buttons.length) return
  event.preventDefault()
  const index = buttons.indexOf(document.activeElement as HTMLButtonElement)
  const next =
    event.key === 'Home'
      ? 0
      : event.key === 'End'
        ? buttons.length - 1
        : event.key === 'ArrowDown'
          ? (index + 1) % buttons.length
          : (index - 1 + buttons.length) % buttons.length
  buttons[next]?.focus()
}
const summary = computed(
  () => confirmed.value?.name ?? (chat.effectiveSelection ? '原方案不可选' : '选择模型'),
)
const reasoningSummary = computed(() => {
  const reasoning = chat.effectiveSelection?.reasoning
  return !reasoning
    ? ''
    : reasoning.mode === 'effort'
      ? reasoning.effort
      : reasoning.mode === 'budget'
        ? String(reasoning.budget_tokens)
        : modeLabels[reasoning.mode]
})
// 同时呈现当前不可用原因和先前操作提醒，避免旧的冲突提醒遮住新的推理限制。
const feedback = computed(() =>
  [...new Set([choices.error, chat.selectionProblem, chat.selectionNotice].filter(Boolean))].join(
    '；',
  ),
)
/** 页面首次进入及重新激活时同步选项和活动会话，不自动替换失效选择。 */
function refresh(): void {
  if (!document.hidden) void chat.refreshChoices()
}
onMounted(() => {
  refresh()
  window.addEventListener('focus', refresh)
  document.addEventListener('visibilitychange', refresh)
})
onBeforeUnmount(() => {
  window.removeEventListener('focus', refresh)
  document.removeEventListener('visibilitychange', refresh)
  chat.selectionEditing = false
})
</script>
<template>
  <section class="chat-model-selector" aria-label="聊天模型状态">
    <PopoverRoot :open="open" @update:open="setOpen">
      <PopoverTrigger as-child>
        <button
          type="button"
          class="chat-model-trigger"
          aria-label="选择聊天模型"
          :title="feedback || summary"
        >
          <AlertCircle v-if="feedback" :size="14" class="chat-model-warning" aria-hidden="true" />
          <span class="chat-model-name">{{ summary }}</span>
          <span v-if="reasoningSummary" class="chat-model-reasoning">{{ reasoningSummary }}</span>
          <ChevronDown :size="14" aria-hidden="true" />
        </button>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent
          class="chat-model-popover"
          side="top"
          align="end"
          :side-offset="10"
          :collision-padding="12"
        >
          <form aria-label="聊天模型选择" novalidate @submit.stop.prevent="apply">
            <div class="chat-model-menu-heading">
              <strong>选择模型</strong
              ><button type="button" :disabled="choices.loading" @click="refresh">
                刷新模型选项
              </button>
            </div>
            <div
              class="chat-model-options"
              role="listbox"
              aria-label="聊天模型方案"
              :aria-disabled="locked || choices.loading"
              @keydown="navigateModels"
            >
              <div
                v-for="provider in choices.options?.providers ?? []"
                :key="provider.provider_configuration_id"
                role="group"
                :aria-label="provider.name"
              >
                <p class="chat-model-group">{{ provider.name }}</p>
                <button
                  v-for="entry in provider.models"
                  :key="entry.model_configuration_id"
                  type="button"
                  role="option"
                  :aria-selected="
                    entry.model_configuration_id === confirmed?.model_configuration_id
                  "
                  :tabindex="
                    entry.model_configuration_id ===
                    (confirmed?.model_configuration_id ?? choices.models[0]?.model_configuration_id)
                      ? 0
                      : -1
                  "
                  :disabled="locked || choices.loading"
                  :data-model-id="entry.model_configuration_id"
                  @click="changeModel(entry.model_configuration_id)"
                >
                  <span
                    ><span class="chat-model-option-name">{{ entry.name }}</span
                    ><small>{{ entry.display_name }}</small></span
                  >
                  <Check
                    v-if="entry.model_configuration_id === confirmed?.model_configuration_id"
                    :size="16"
                    aria-hidden="true"
                  />
                </button>
              </div>
            </div>
            <p v-if="choices.loading && !choices.options" role="status">正在读取模型选项…</p>
            <p v-else-if="!choices.error && !choices.models.length" class="chat-model-empty">
              暂无可用模型，你可以先写草稿，配置完成后再发送。
            </p>
            <fieldset
              v-if="model && draft"
              class="chat-reasoning-settings"
              :disabled="locked || choices.loading"
            >
              <p v-if="model.reasoning_control.mode === 'fixed'" class="chat-model-fixed">
                固定推理设置 · {{ modeLabels[model.reasoning_control.default.mode]
                }}<span v-if="model.reasoning_control.default.mode === 'effort'">
                  · {{ model.reasoning_control.default.effort }}</span
                ><span v-else-if="model.reasoning_control.default.mode === 'budget'">
                  · {{ model.reasoning_control.default.budget_tokens }}</span
                >
              </p>
              <template v-else>
                <label
                  >推理方式<select
                    name="chat_reasoning_mode"
                    :value="draft.reasoning.mode"
                    @change="changeMode"
                  >
                    <option
                      v-if="!model.reasoning_control.allowed_modes.includes(draft.reasoning.mode)"
                      :value="draft.reasoning.mode"
                      disabled
                    >
                      原设置已超出允许范围
                    </option>
                    <option
                      v-for="mode in model.reasoning_control.allowed_modes"
                      :key="mode"
                      :value="mode"
                    >
                      {{ modeLabels[mode] }}
                    </option>
                  </select></label
                >
                <label v-if="draft.reasoning.mode === 'effort'"
                  >推理档位<select
                    name="chat_effort"
                    :value="draft.reasoning.effort"
                    @change="changeEffort"
                  >
                    <option
                      v-for="effort in model.reasoning_control.effort_options"
                      :key="effort"
                      :value="effort"
                    >
                      {{ effort }}
                    </option>
                  </select></label
                >
                <label v-if="draft.reasoning.mode === 'budget' && model.reasoning_control.budget"
                  >思考预算<input
                    name="chat_budget"
                    type="number"
                    step="1"
                    :min="model.reasoning_control.budget.min"
                    :max="model.reasoning_control.budget.max"
                    :value="draft.reasoning.budget_tokens"
                    @input="changeBudget"
                  /><small
                    >{{ model.reasoning_control.budget.min }}–{{
                      model.reasoning_control.budget.max
                    }}
                    tokens，确认后保存。</small
                  ></label
                >
                <div
                  v-if="draft.reasoning.mode === 'budget' || chat.selectionEditing"
                  class="chat-selection-actions"
                >
                  <button type="submit">应用选择</button
                  ><button v-if="chat.selectionEditing" type="button" @click="reset">
                    取消修改
                  </button>
                </div>
              </template>
            </fieldset>
            <p v-if="error" role="alert">{{ error }}</p>
            <p v-if="feedback" role="alert">{{ feedback }}</p>
            <p v-if="chat.activeConversation?.selectionSaving" role="status">正在保存会话选择…</p>
            <p v-if="chat.isSending">正在生成，结束后可切换模型。</p>
            <footer class="chat-model-menu-footer">
              <RouterLink to="/models">前往模型管理</RouterLink>
            </footer>
          </form>
        </PopoverContent>
      </PopoverPortal>
    </PopoverRoot>
    <span v-if="feedback && !open" class="chat-model-accessible-status" role="status">{{
      feedback
    }}</span>
    <span
      v-if="chat.activeConversation?.selectionSaving && !open"
      class="chat-model-accessible-status"
      role="status"
      >正在保存会话选择…</span
    >
  </section>
</template>
<style>
/* 选择器浮层通过 Portal 挂载，样式不依赖输入框祖先；避让由 Reka 根据可用视口计算。 */
.chat-model-selector {
  min-width: 0;
  max-width: 240px;
}
.chat-model-trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  max-width: 100%;
  min-height: 32px;
  padding: 6px 8px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.chat-model-trigger:hover,
.chat-model-trigger[data-state='open'] {
  background: var(--surface-hover);
  color: var(--text);
}
.chat-model-trigger:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: 2px;
}
.chat-model-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.chat-model-reasoning {
  color: var(--text-muted);
  white-space: nowrap;
  max-width: 65px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 11px;
}
.chat-model-trigger svg {
  flex-shrink: 0;
}
.chat-model-warning {
  color: var(--danger);
}
.chat-model-accessible-status {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
.chat-model-popover {
  z-index: var(--z-menu);
  width: min(360px, calc(100vw - 24px));
  max-height: min(560px, var(--reka-popover-content-available-height));
  overflow: auto;
  overscroll-behavior: contain;
  padding: 14px;
  border: 1px solid var(--border-strong);
  border-radius: 14px;
  background: var(--surface);
  color: var(--text);
  box-shadow: var(--shadow-popover);
  font-size: 12px;
}
.chat-model-popover p {
  margin: 10px 0;
  line-height: 1.6;
}
.chat-model-menu-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}
.chat-model-popover button {
  cursor: pointer;
  font: inherit;
}
.chat-model-popover button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
.chat-model-menu-heading > button,
.chat-selection-actions > button {
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 7px;
  color: var(--brand);
  background: var(--surface);
}
.chat-model-options {
  max-height: 260px;
  overflow: auto;
  overscroll-behavior: contain;
}
.chat-model-group {
  padding: 0 8px;
  font-size: 11px;
  color: var(--text-muted);
}
.chat-model-options [role='option'] {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  padding: 10px;
  border: 0;
  border-radius: 8px;
  text-align: left;
  background: transparent;
  color: var(--text);
}
.chat-model-options [role='option']:hover,
.chat-model-options [role='option']:focus-visible {
  outline: none;
  background: var(--surface-hover);
}
.chat-model-options [aria-selected='true'] {
  background: var(--brand-soft);
}
.chat-model-options [role='option'] > span {
  min-width: 0;
}
.chat-model-option-name {
  display: block;
  font-size: 13px;
  overflow-wrap: anywhere;
}
.chat-model-options small {
  display: block;
  margin-top: 3px;
  color: var(--text-muted);
  overflow-wrap: anywhere;
}
.chat-reasoning-settings {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 10px;
  border: 0;
  padding: 12px 0 0;
  margin: 12px 0 0;
  border-top: 1px solid var(--border);
}
.chat-reasoning-settings label {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.chat-reasoning-settings select,
.chat-reasoning-settings input {
  width: 100%;
  min-width: 0;
  padding: 8px;
  border: 1px solid var(--border-strong);
  border-radius: 7px;
  background: var(--bg);
  color: var(--text);
  font: inherit;
}
.chat-reasoning-settings small,
.chat-model-fixed {
  color: var(--text-secondary);
}
.chat-selection-actions {
  display: flex;
  gap: 8px;
}
.chat-model-popover [role='alert'] {
  color: var(--danger);
}
.chat-model-menu-footer {
  padding-top: 12px;
  margin-top: 12px;
  border-top: 1px solid var(--border);
}
.chat-model-menu-footer a {
  color: var(--brand);
  text-decoration: none;
}
@media (max-width: 760px) {
  .chat-model-selector {
    max-width: min(220px, calc(100vw - 116px));
  }
  .chat-reasoning-settings input,
  .chat-reasoning-settings select {
    font-size: 16px;
  }
}
</style>
