<!-- 聊天模型控件：只展示允许范围；新会话维护草稿，已有会话通过 PATCH 确认后才允许发送。 -->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useChatStore } from '@/features/chat/store'
import { modeLabels } from '@/features/model-config/validation'
import { useModelSelectionStore } from '../store'
import { decodeSelection, validateSelection } from '../contract'
import type { ConcreteReasoning, ModelSelection } from '../types'
const chat = useChatStore(),
  choices = useModelSelectionStore()
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
watch(() => chat.activeId, reset, { immediate: true })
watch(
  () => chat.effectiveSelection,
  () => {
    if (!chat.selectionEditing) reset()
  },
  { deep: true },
)
/** 显式提交完整具体值；失败保留当前控件草稿，绝不自动重发聊天。 */
async function apply(): Promise<void> {
  if (!draft.value || !model.value || locked.value) return
  if (model.value.reasoning_control.mode === 'fixed')
    draft.value.reasoning = { ...model.value.reasoning_control.default }
  error.value = validateSelection(draft.value, model.value)
  if (error.value) return
  const target = chat.activeId
  if ((await chat.chooseSelection(decodeSelection(draft.value))) && chat.activeId === target)
    reset()
}
/** 更换方案时复制其具体默认，已有会话立即保存，不能修改选项缓存。 */
async function changeModel(event: Event): Promise<void> {
  const id = (event.target as HTMLSelectElement).value,
    next = choices.models.find((model) => model.model_configuration_id === id)
  if (!next) return
  draft.value = { model_configuration_id: id, reasoning: { ...next.reasoning_control.default } }
  chat.selectionEditing = true
  await apply()
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
    <details class="chat-model-picker">
      <summary>
        模型 · {{ confirmed?.name ?? (chat.effectiveSelection ? '原方案不可选' : '请选择模型')
        }}<span v-if="chat.effectiveSelection">
          · {{ modeLabels[chat.effectiveSelection.reasoning.mode]
          }}{{
            chat.effectiveSelection.reasoning.mode === 'effort'
              ? ` · ${chat.effectiveSelection.reasoning.effort}`
              : chat.effectiveSelection.reasoning.mode === 'budget'
                ? ` · ${chat.effectiveSelection.reasoning.budget_tokens}`
                : ''
          }}</span
        >
      </summary>
      <form aria-label="聊天模型选择" novalidate @submit.prevent="apply">
        <fieldset :disabled="locked || choices.loading">
          <label
            >模型方案<select
              name="chat_model"
              aria-label="聊天模型方案"
              :value="draft?.model_configuration_id ?? ''"
              @change="changeModel"
            >
              <option value="" disabled>请选择模型方案</option>
              <option v-if="draft && !model" :value="draft.model_configuration_id" disabled>
                原模型方案不可用，请重新选择
              </option>
              <optgroup
                v-for="provider in choices.options?.providers ?? []"
                :key="provider.provider_configuration_id"
                :label="provider.name"
              >
                <option
                  v-for="model in provider.models"
                  :key="model.model_configuration_id"
                  :value="model.model_configuration_id"
                >
                  {{ model.name }} · {{ model.display_name }}
                </option>
              </optgroup>
            </select></label
          >
          <template v-if="model && draft">
            <p v-if="model.reasoning_control.mode === 'fixed'">
              固定推理设置 · {{ modeLabels[model.reasoning_control.default.mode]
              }}{{
                model.reasoning_control.default.mode === 'effort'
                  ? ` · ${model.reasoning_control.default.effort}`
                  : model.reasoning_control.default.mode === 'budget'
                    ? ` · ${model.reasoning_control.default.budget_tokens}`
                    : ''
              }}
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
            </template>
            <div class="chat-selection-actions">
              <button type="submit">应用选择</button
              ><button v-if="chat.selectionEditing" type="button" @click="reset">取消修改</button>
            </div>
          </template>
        </fieldset>
        <p v-if="error" role="alert">{{ error }}</p>
        <p v-if="chat.activeConversation?.selectionSaving" role="status">正在保存会话选择…</p>
        <p v-if="locked && chat.isSending">正在生成，结束后可切换模型。</p>
      </form>
    </details>
    <p v-if="choices.loading && !choices.options" role="status">正在读取模型选项…</p>
    <p v-else-if="choices.error" role="alert">{{ choices.error }}</p>
    <p v-else-if="!choices.models.length">暂无可用模型，你可以先写草稿，配置完成后再发送。</p>
    <p
      v-if="choices.options && !choices.error && chat.selectionProblem"
      :role="chat.activeConversation?.modelSelectionIssue ? 'alert' : undefined"
    >
      {{ chat.selectionProblem }}
    </p>
    <p v-if="chat.selectionNotice" role="alert">{{ chat.selectionNotice }}</p>
    <button type="button" :disabled="choices.loading" @click="refresh">刷新模型选项</button>
    <RouterLink to="/models">前往模型管理</RouterLink>
  </section>
</template>
<style scoped>
.chat-model-selector {
  z-index: 2;
  display: flex;
  flex-shrink: 0;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 8px 14px;
  padding: 7px 20px;
  font-size: 12px;
  color: var(--text-secondary);
}
.chat-model-selector p {
  margin: 0;
}
.chat-model-selector a {
  color: var(--brand);
  text-decoration: none;
}
.chat-model-picker {
  position: relative;
  min-width: 0;
  max-width: 100%;
}
summary {
  cursor: pointer;
  color: var(--brand);
  overflow-wrap: anywhere;
}
form {
  position: absolute;
  inset: 100% auto auto 0;
  width: min(410px, calc(100vw - 40px));
  max-height: 55dvh;
  overflow: auto;
  padding: 18px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
  box-shadow: 0 10px 30px #0002;
  z-index: 5;
}
fieldset {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 14px;
  border: 0;
  margin: 0;
  padding: 0;
}
label {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
select,
input {
  min-width: 0;
  width: 100%;
  padding: 9px;
  border: 1px solid var(--border-strong);
  border-radius: 7px;
  background: var(--bg);
  color: var(--text);
  font: inherit;
}
button {
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--surface);
  color: var(--brand);
  font: inherit;
  padding: 5px 8px;
}
.chat-selection-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
@media (max-width: 760px) {
  form {
    position: fixed;
    inset: 110px 16px auto;
    width: auto;
    max-height: 60dvh;
  }
  select,
  input {
    font-size: 16px;
  }
}
</style>
