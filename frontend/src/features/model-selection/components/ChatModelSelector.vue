<!-- 输入区模型下拉：仅选择模型及进入管理页，打开菜单和窗口恢复时自动同步允许范围。 -->
<script setup lang="ts">
import UiFeedback from '@/shared/components/ui/UiFeedback.vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { PopoverRoot, PopoverTrigger, PopoverPortal, PopoverContent } from 'reka-ui'
import { ChevronDown, Check, AlertCircle } from '@lucide/vue'
import { useChatStore } from '@/features/chat/store'
import { useAuthStore } from '@/features/auth/store'
import { useModelSelectionStore } from '../store'
const chat = useChatStore(),
  choices = useModelSelectionStore()
const auth = useAuthStore()
const open = ref(false)
const listbox = ref<HTMLElement | null>(null)
const confirmed = computed(() =>
  choices.models.find(
    (model) => model.model_configuration_id === chat.effectiveSelection?.model_configuration_id,
  ),
)
const locked = computed(
  () => chat.isSending || chat.inputBlocked || !!chat.activeConversation?.selectionSaving,
)
const summary = computed(
  () => confirmed.value?.name ?? (chat.effectiveSelection ? '原方案不可选' : '选择模型'),
)
const feedback = computed(() =>
  [
    ...new Set(
      [choices.error, chat.selectionProblem, chat.selectionNotice].filter(
        (item) => item && item !== '请选择模型方案',
      ),
    ),
  ].join('；'),
)
/** 用户明确选择时提交模型默认参数；不把其他控件的未确认草稿带入新模型。 */
async function changeModel(id: string): Promise<void> {
  const model = choices.models.find((item) => item.model_configuration_id === id)
  if (!model || locked.value || choices.loading) return
  const target = chat.activeId
  if (
    (await chat.chooseSelection({
      model_configuration_id: id,
      reasoning: { ...model.reasoning_control.default },
    })) &&
    chat.activeId === target
  ) {
    chat.selectionEditing = false
    open.value = false
  }
}
/** 自动同步当前允许范围，不替换已经确认的选择或重发聊天。 */
function refresh(): void {
  if (!document.hidden) void chat.refreshChoices()
}
/** 打开模型菜单时同步选项，以自动更新替代手动刷新按钮。 */
function setOpen(value: boolean): void {
  open.value = value
  if (value) refresh()
}
/** 打开时聚焦模型列表，避免顶部管理链接抢占选模焦点；加载中先聚焦列表容器。 */
function focusModels(event: Event): void {
  event.preventDefault()
  const selected = listbox.value?.querySelector<HTMLButtonElement>(
    '[role="option"][aria-selected="true"]:not(:disabled)',
  )
  const first = listbox.value?.querySelector<HTMLButtonElement>('[role="option"]:not(:disabled)')
  ;(selected ?? first ?? listbox.value)?.focus()
}
/** 键盘方向键只移动焦点，Enter 或空格才确认选择。 */
function navigateModels(event: KeyboardEvent): void {
  if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return
  const buttons = [
    ...(event.currentTarget as HTMLElement).querySelectorAll<HTMLButtonElement>(
      '[role="option"]:not(:disabled)',
    ),
  ]
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
  const target = index < 0 && event.key === 'ArrowUp' ? buttons.length - 1 : next
  buttons[target]?.focus()
}
// 本地临时 ID 绑定服务端 ID 仍是同一对象；只有真正切换会话才关闭菜单。
watch(
  () => chat.activeConversation,
  () => {
    open.value = false
  },
)
onMounted(() => {
  refresh()
  window.addEventListener('focus', refresh)
  document.addEventListener('visibilitychange', refresh)
})
onBeforeUnmount(() => {
  window.removeEventListener('focus', refresh)
  document.removeEventListener('visibilitychange', refresh)
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
          @open-auto-focus="focusModels"
        >
          <div aria-label="聊天模型选择">
            <div class="chat-model-menu-heading">
              <strong>选择模型</strong
              ><RouterLink v-if="auth.can('model:manage')" to="/models">前往模型管理</RouterLink>
            </div>
            <div
              ref="listbox"
              class="chat-model-options"
              role="listbox"
              tabindex="-1"
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
            <UiFeedback v-if="feedback" compact>{{ feedback }}</UiFeedback>
            <p v-if="chat.activeConversation?.selectionSaving" role="status">正在保存会话选择…</p>
            <p v-if="chat.isSending">正在生成，结束后可切换模型。</p>
          </div>
        </PopoverContent>
      </PopoverPortal>
    </PopoverRoot>
    <UiFeedback v-if="feedback && !open" compact :message="feedback" />
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
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
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
  width: min(300px, calc(100vw - 24px));
  max-height: min(420px, var(--reka-popover-content-available-height));
  overflow: auto;
  overscroll-behavior: contain;
  padding: 10px;
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
  margin-bottom: 6px;
  padding: 3px 3px 9px;
  border-bottom: 1px solid var(--border);
}
.chat-model-popover button {
  cursor: pointer;
  font: inherit;
}
.chat-model-popover button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
.chat-model-menu-heading > button {
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 7px;
  color: var(--brand);
  background: var(--surface);
}
.chat-model-options {
  max-height: 230px;
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
  padding: 8px;
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
  font-size: 12px;
  overflow-wrap: anywhere;
}
.chat-model-options small {
  display: block;
  margin-top: 3px;
  color: var(--text-muted);
  overflow-wrap: anywhere;
}
.chat-model-popover [role='alert'] {
  color: var(--danger);
}
.chat-model-menu-heading a {
  color: var(--brand);
  font-size: 10px;
  text-decoration: none;
  white-space: nowrap;
}
@media (max-width: 760px) {
  .chat-model-selector {
    max-width: min(220px, calc(100vw - 116px));
  }
}
</style>
