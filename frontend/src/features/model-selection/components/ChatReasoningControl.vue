<!-- 输入区思考强度：以单一滑块包含关闭档，遵循后端允许范围及会话确认版本。 -->
<script setup lang="ts">
import UiFeedback from '@/shared/components/ui/UiFeedback.vue'
import UiInput from '@/shared/components/ui/UiInput.vue'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { PopoverRoot, PopoverTrigger, PopoverPortal, PopoverContent } from 'reka-ui'
import { ChevronDown, Sparkles } from '@lucide/vue'
import { useChatStore } from '@/features/chat/store'
import { effortLabels } from '@/features/model-config/validation'
import { useModelSelectionStore } from '../store'
import { decodeSelection, validateSelection } from '../contract'
import type { ConcreteReasoning, ModelSelection } from '../types'

const chat = useChatStore(),
  choices = useModelSelectionStore()
const open = ref(false),
  error = ref('')
const draft = ref<ModelSelection | null>(null)
const kind = ref<'effort' | 'budget'>('effort')
const model = computed(() =>
  choices.models.find(
    (item) => item.model_configuration_id === chat.effectiveSelection?.model_configuration_id,
  ),
)
const control = computed(() => model.value?.reasoning_control)
const locked = computed(
  () =>
    chat.isSending ||
    chat.inputBlocked ||
    !!chat.activeConversation?.selectionSaving ||
    choices.loading,
)
const canAdjust = computed(() => control.value?.mode === 'selectable')
const allowsOff = computed(
  () => control.value?.mode === 'selectable' && control.value.allowed_modes.includes('off'),
)
const budget = computed(() => (control.value?.mode === 'selectable' ? control.value.budget : null))
// 档位保持后端顺序，关闭只在明确允许时作为最左档；预算用额外的零档表示关闭。
const steps = computed<ConcreteReasoning[]>(() =>
  control.value?.mode === 'selectable'
    ? [
        ...(allowsOff.value ? [{ mode: 'off' } as const] : []),
        ...control.value.effort_options.map((effort) => ({ mode: 'effort' as const, effort })),
      ]
    : [],
)
const sliderMax = computed(() =>
  kind.value === 'budget' && budget.value
    ? budget.value.max - budget.value.min + Number(allowsOff.value)
    : Math.max(0, steps.value.length - 1),
)
const sliderValue = computed(() => {
  const reasoning = draft.value?.reasoning
  if (!reasoning || reasoning.mode === 'off') return 0
  if (reasoning.mode === 'budget' && budget.value)
    return Math.max(0, reasoning.budget_tokens - budget.value.min + Number(allowsOff.value))
  if (reasoning.mode === 'effort')
    return Math.max(
      0,
      steps.value.findIndex((step) => step.mode === 'effort' && step.effort === reasoning.effort),
    )
  return 0
})
const progress = computed(() =>
  sliderMax.value && Number.isFinite(sliderValue.value)
    ? (sliderValue.value / sliderMax.value) * 100 + '%'
    : '0%',
)
const tickLabels = computed(() =>
  kind.value === 'budget' && budget.value
    ? [
        allowsOff.value ? '关闭' : budget.value.min.toLocaleString(),
        budget.value.max.toLocaleString(),
      ]
    : steps.value.map((step) => describe(step)),
)
const summary = computed(() => describe(chat.effectiveSelection?.reasoning))
const draftSummary = computed(() => describe(draft.value?.reasoning))

/** 将具体推理值转为紧凑的展示标签，未完成预算输入显示占位符。 */
function describe(reasoning?: ConcreteReasoning): string {
  if (!reasoning) return '思考强度'
  if (reasoning.mode === 'off') return '关闭'
  if (reasoning.mode === 'effort') return effortLabels[reasoning.effort] ?? reasoning.effort
  return Number.isFinite(reasoning.budget_tokens)
    ? reasoning.budget_tokens.toLocaleString() + ' tokens'
    : '—'
}
/** 恢复已确认值及其滑块形式；关闭状态仍保留可打开、可重新启用的强度入口。 */
function reset(): void {
  draft.value = chat.effectiveSelection ? decodeSelection(chat.effectiveSelection) : null
  const reasoning = draft.value?.reasoning
  if (reasoning && reasoning.mode !== 'off') kind.value = reasoning.mode
  else if (
    control.value?.mode === 'selectable' &&
    !control.value.allowed_modes.includes(kind.value)
  )
    kind.value = control.value.allowed_modes.find((mode) => mode !== 'off') ?? 'effort'
  error.value = ''
  chat.selectionEditing = false
}
/** 校验并提交具体推理值，失败保留滑块草稿，迟到响应不覆盖另一会话。 */
async function apply(): Promise<boolean> {
  if (!draft.value || !model.value || locked.value) return false
  error.value = validateSelection(draft.value, model.value)
  if (error.value) return false
  const target = chat.activeId
  if ((await chat.chooseSelection(decodeSelection(draft.value))) && chat.activeId === target) {
    reset()
    return true
  }
  return false
}
/** 滑动仅编辑草稿；释放滑块或键盘确认后才保存，零档不会发送非法零预算。 */
function slide(event: Event): void {
  if (!draft.value || locked.value) return
  const value = (event.target as HTMLInputElement).valueAsNumber
  if (kind.value === 'budget' && budget.value)
    draft.value.reasoning =
      allowsOff.value && value === 0
        ? { mode: 'off' }
        : { mode: 'budget', budget_tokens: value - Number(allowsOff.value) + budget.value.min }
  else {
    const step = steps.value[value]
    if (!step) return
    draft.value.reasoning = { ...step }
  }
  chat.selectionEditing = true
}
/** 同时支持档位和预算时切换设置形式；关闭状态只切换界面，不暗中开启思考。 */
async function changeKind(mode: 'effort' | 'budget'): Promise<void> {
  if (
    !draft.value ||
    locked.value ||
    control.value?.mode !== 'selectable' ||
    !control.value.allowed_modes.includes(mode)
  )
    return
  kind.value = mode
  if (draft.value.reasoning.mode === 'off') return
  draft.value.reasoning =
    control.value.default.mode === mode
      ? { ...control.value.default }
      : mode === 'effort'
        ? { mode, effort: control.value.effort_options[0]! }
        : { mode, budget_tokens: budget.value!.min }
  chat.selectionEditing = true
  await apply()
}
/** 保留精确预算输入的无效值供表单提示，不静默裁剪或提前写入。 */
function editBudget(event: Event): void {
  if (!draft.value || locked.value) return
  draft.value.reasoning = {
    mode: 'budget',
    budget_tokens: (event.target as HTMLInputElement).valueAsNumber,
  }
  chat.selectionEditing = true
}
/** 关闭浮层取消未提交输入，重新打开时展示当前确认值。 */
function setOpen(value: boolean): void {
  open.value = value
  reset()
}
// 只在会话或模型身份改变时关闭；保存同一模型的关闭档不会卸载浮层。
watch(
  [() => chat.activeId, () => chat.effectiveSelection?.model_configuration_id],
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
watch(control, () => {
  if (!chat.selectionEditing) reset()
})
onBeforeUnmount(() => {
  chat.selectionEditing = false
})
</script>

<template>
  <div class="chat-reasoning-control" role="group" aria-label="推理设置">
    <PopoverRoot :open="open" @update:open="setOpen">
      <PopoverTrigger as-child>
        <button
          type="button"
          class="reasoning-strength-trigger"
          aria-label="设置推理强度"
          :disabled="locked || !canAdjust"
          :title="canAdjust ? '调整思考强度' : '固定推理设置 · ' + summary"
        >
          <Sparkles :size="14" aria-hidden="true" /><span>{{ summary }}</span
          ><ChevronDown v-if="canAdjust" :size="12" aria-hidden="true" />
        </button>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent
          class="reasoning-popover"
          side="top"
          align="start"
          :side-offset="10"
          :collision-padding="12"
        >
          <form aria-label="思考强度设置" novalidate @submit.stop.prevent="apply">
            <div class="reasoning-popover-heading">
              <Sparkles :size="14" aria-hidden="true" />
              <div>
                <output class="reasoning-value">{{ draftSummary }}</output>
                <p>{{ model?.name }}</p>
              </div>
            </div>
            <div
              v-if="
                control?.mode === 'selectable' &&
                control.allowed_modes.includes('effort') &&
                control.allowed_modes.includes('budget')
              "
              class="reasoning-kind"
            >
              <button
                type="button"
                :aria-pressed="kind === 'effort'"
                :disabled="locked"
                @click="changeKind('effort')"
              >
                档位
              </button>
              <button
                type="button"
                :aria-pressed="kind === 'budget'"
                :disabled="locked"
                @click="changeKind('budget')"
              >
                预算
              </button>
            </div>
            <fieldset :disabled="locked">
              <div class="reasoning-track">
                <input
                  type="range"
                  class="reasoning-slider"
                  :aria-label="kind === 'budget' ? '思考预算滑块' : '推理强度'"
                  :aria-valuetext="draftSummary"
                  min="0"
                  :max="sliderMax"
                  step="1"
                  :value="sliderValue"
                  :style="{ '--slider-progress': progress }"
                  :disabled="sliderMax === 0 || locked"
                  @input="slide"
                  @change="apply"
                />
                <div class="reasoning-stops" aria-hidden="true">
                  <i v-for="index in kind === 'budget' ? 5 : steps.length" :key="index" />
                </div>
              </div>
              <div class="reasoning-ticks">
                <span v-for="label in tickLabels" :key="label">{{ label }}</span>
              </div>
              <template v-if="kind === 'budget' && draft?.reasoning.mode === 'budget' && budget">
                <label class="reasoning-budget"
                  >思考预算<UiInput
                    name="chat_budget"
                    type="number"
                    size="sm"
                    step="1"
                    :min="budget.min"
                    :max="budget.max"
                    :value="draft.reasoning.budget_tokens"
                    @input="editBudget"
                /></label>
                <button type="submit" class="reasoning-apply">应用预算</button>
              </template>
            </fieldset>
            <UiFeedback v-if="error" compact>{{ error }}</UiFeedback>
          </form>
        </PopoverContent>
      </PopoverPortal>
    </PopoverRoot>
  </div>
</template>

<style>
.chat-reasoning-control {
  display: flex;
  align-items: center;
  min-width: 0;
}
.reasoning-strength-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 30px;
  max-width: 190px;
  padding: 5px 8px;
  border: 1px solid var(--border);
  border-radius: 16px;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 11px;
  white-space: nowrap;
  cursor: pointer;
}
.reasoning-strength-trigger > span {
  overflow: hidden;
  text-overflow: ellipsis;
}
.reasoning-strength-trigger svg {
  flex-shrink: 0;
}
.reasoning-strength-trigger:disabled {
  cursor: default;
  opacity: 0.6;
}
.reasoning-strength-trigger:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: 2px;
}
.reasoning-popover {
  z-index: var(--z-menu);
  width: min(264px, calc(100vw - 24px));
  max-height: var(--reka-popover-content-available-height);
  overflow: auto;
  padding: 14px;
  border: 1px solid var(--border-strong);
  border-radius: 16px;
  background: var(--surface);
  color: var(--text);
  box-shadow: var(--shadow-popover);
  font-size: 12px;
}
.reasoning-popover-heading {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr) 16px;
  align-items: start;
  gap: 8px;
  color: var(--text-muted);
}
.reasoning-popover-heading > div {
  min-width: 0;
  text-align: center;
}
.reasoning-popover-heading p {
  margin: 4px 0 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 10px;
}
.reasoning-value {
  display: block;
  color: var(--brand);
  font-size: 15px;
  font-weight: 550;
  line-height: 1.25;
}
.reasoning-popover fieldset {
  margin: 14px 0 0;
  padding: 0;
  border: 0;
  min-width: 0;
}
.reasoning-track {
  position: relative;
}
.reasoning-slider {
  appearance: none;
  display: block;
  width: 100%;
  height: 22px;
  margin: 0;
  border: 0;
  border-radius: 999px;
  background: linear-gradient(
    to right,
    var(--brand) 0 var(--slider-progress),
    var(--surface-hover) var(--slider-progress) 100%
  );
  cursor: pointer;
}
.reasoning-slider::-webkit-slider-thumb {
  appearance: none;
  position: relative;
  z-index: 1;
  width: 26px;
  height: 26px;
  border: 1px solid var(--border);
  border-radius: 50%;
  background: var(--surface);
  box-shadow: 0 1px 4px rgb(0 0 0 / 14%);
}
.reasoning-slider::-moz-range-thumb {
  width: 26px;
  height: 26px;
  border: 1px solid var(--border);
  border-radius: 50%;
  background: var(--surface);
  box-shadow: 0 1px 4px rgb(0 0 0 / 14%);
}
.reasoning-slider:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: 4px;
}
.reasoning-stops {
  position: absolute;
  inset: 0 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  pointer-events: none;
}
.reasoning-stops i {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--text-muted);
  opacity: 0.5;
}
.reasoning-ticks {
  display: flex;
  justify-content: space-between;
  gap: 6px;
  margin-top: 9px;
  color: var(--text-muted);
  font-size: 9px;
}
.reasoning-ticks span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 60px;
}
.reasoning-budget {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 14px;
  font-size: 11px;
}
.reasoning-budget .ui-input {
  width: 110px;
  min-width: 0;
}
.reasoning-apply {
  margin-top: 10px;
  padding: 7px 12px;
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--brand-soft);
  color: var(--brand);
  cursor: pointer;
}
.reasoning-kind {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}
.reasoning-kind button {
  flex: 1;
  border: 1px solid var(--border);
  border-radius: 7px;
  padding: 5px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
}
.reasoning-kind [aria-pressed='true'] {
  background: var(--brand-soft);
  color: var(--brand);
}
.reasoning-popover [role='alert'] {
  color: var(--danger);
  line-height: 1.6;
}
</style>
