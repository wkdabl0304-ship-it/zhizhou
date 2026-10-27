<!-- 通用模态框：以 Reka 管理 Portal、焦点、Esc 和滚动锁，支持居中宽弹窗与右侧表单抽屉。 -->
<script setup lang="ts">
import {
  DialogRoot,
  DialogPortal,
  DialogOverlay,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from 'reka-ui'
import { X } from '@lucide/vue'
import { computed, nextTick, onUnmounted, watch } from 'vue'
import { useDialogLayer } from '@/shared/composables/useDialogLayer'
import UiIconButton from './UiIconButton.vue'
const props = withDefaults(
  defineProps<{
    open: boolean
    title: string
    description?: string
    size?: 'sm' | 'md' | 'lg' | 'xl'
    layout?: 'content' | 'panel'
    height?: string
    busy?: boolean
    closeOnEscape?: boolean
    closeOnOutside?: boolean
    initialFocus?: string
    layer?: number
    drawer?: boolean
    wide?: boolean
    editor?: boolean
    returnFocus?: HTMLElement | null
    closeDisabled?: boolean
  }>(),
  { closeOnEscape: true, closeOnOutside: true },
)
const emit = defineEmits<{ 'update:open': [value: boolean]; openAutoFocus: [event: Event] }>()
// Portal 保留 Vue 的注入链；每层遮罩必须高于上一层内容，确认框才能覆盖编辑弹窗。
const { overlayStyle, contentStyle } = useDialogLayer(props.layer)
const blocked = computed(() => props.busy || props.closeDisabled)
const style = computed(() => ({
  ...contentStyle,
  width: props.size
    ? `min(${{ sm: 400, md: 480, lg: 680, xl: 1120 }[props.size]}px, calc(100vw - 32px))`
    : undefined,
  height: props.height,
}))
// 编辑开始会禁用原卡片按钮；调用方可提前保存触发器，避免浏览器清空焦点后丢失返回位置。
let previous = props.returnFocus ?? document.activeElement
// 常驻组件从关闭切到打开时重新记录触发器，不能一直使用首次挂载时的焦点。
watch(
  () => props.open,
  (open) => {
    if (open) previous = props.returnFocus ?? document.activeElement
  },
  { flush: 'sync' },
)
/** 请求关闭当前层，保存期间统一拦截关闭按钮、Esc 和遮罩关闭。 */
function requestClose(value = false): void {
  if (!blocked.value) emit('update:open', value)
}
/** 按调用方配置聚焦内容中的控件，默认仍交给 Reka，并开放事件供特殊表单定制。 */
function focusInitial(event: Event): void {
  emit('openAutoFocus', event)
  if (event.defaultPrevented || !props.initialFocus || !(event.target instanceof HTMLElement))
    return
  const target = event.target.querySelector<HTMLElement>(props.initialFocus)
  if (target) {
    event.preventDefault()
    target.focus()
  }
}
/** 根据关闭策略拦截 Esc，嵌套层始终由 Reka 分发到最上层。 */
function escape(event: Event): void {
  if (blocked.value || props.closeOnEscape === false) event.preventDefault()
}
/** 根据关闭策略拦截外部交互，忙碌表单不会被遮罩点击提前关闭。 */
function outside(event: Event): void {
  if (blocked.value || props.closeOnOutside === false) event.preventDefault()
}
/** 模态关闭后恢复触发元素；列表重绘移除触发器时回到页面标题。 */
function restoreFocus(event: Event): void {
  event.preventDefault()
  restoreTarget()
}
/** 在焦点约束已释放后恢复仍存在的入口，避免嵌套弹层卸载互相抢焦点。 */
function restoreTarget(): void {
  if (previous instanceof HTMLElement && previous.isConnected && !previous.matches(':disabled'))
    previous.focus()
  else {
    // 编辑器与放弃确认可能同帧卸载；确认层不能把已恢复到主面板的焦点再次移到页面外。
    const dialogs = document.querySelectorAll<HTMLElement>('[data-ui-dialog][data-state="open"]')
    const remaining = dialogs[dialogs.length - 1]
    if (remaining) {
      if (!remaining.contains(document.activeElement)) remaining.focus()
      return
    }
    const active = document.activeElement
    if (active instanceof HTMLElement && active !== document.body && active.isConnected) return
    document.querySelector<HTMLElement>('main h1[tabindex]')?.focus()
  }
}
// 页面使用 v-if 移除整个 DialogRoot 时，内部事件可能随祖先卸载而停止转发。
// Reka 2.11 的 FocusScope 在下一宏任务释放焦点约束；其后补回入口，兼容多层同帧卸载。
onUnmounted(() => {
  if (!props.open) return
  void nextTick(() => {
    setTimeout(restoreTarget, 0)
  })
})
</script>
<template>
  <DialogRoot :open="open" @update:open="requestClose">
    <DialogPortal>
      <DialogOverlay class="config-modal-overlay" :style="overlayStyle" />
      <DialogContent
        class="config-modal ui-modal"
        data-ui-dialog
        :class="{
          'config-modal--drawer': drawer,
          'config-modal--wide': wide,
          'config-modal--editor': editor || layout === 'panel',
        }"
        :style="style"
        @open-auto-focus="focusInitial"
        @escape-key-down="escape"
        @interact-outside="outside"
        @close-auto-focus="restoreFocus"
      >
        <header class="config-modal-heading">
          <div>
            <DialogTitle>{{ title }}</DialogTitle
            ><DialogDescription :class="{ 'sr-only': !description }">{{
              description || title
            }}</DialogDescription>
          </div>
          <slot name="header-actions" />
          <UiIconButton label="关闭" :disabled="blocked" @click="requestClose()"
            ><X :size="18"
          /></UiIconButton>
        </header>
        <div class="config-modal-body"><slot /></div>
        <footer v-if="$slots.footer" class="ui-modal-footer">
          <slot name="footer" :close="requestClose" />
        </footer>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
<style>
.config-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--z-overlay);
  background: var(--overlay);
}
.config-modal {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: var(--z-drawer);
  width: min(440px, calc(100vw - 32px));
  max-height: calc(100dvh - 32px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-lg);
  background: var(--surface);
  color: var(--text);
  box-shadow: var(--shadow-popover);
  padding: 24px;
}
.config-modal-heading {
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 20px;
}
.config-modal-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  overscroll-behavior: contain;
}
.config-modal--drawer .config-modal-body {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.config-modal-heading h2 {
  margin: 0 0 7px;
  font-size: 18px;
  font-weight: 500;
}
.config-modal-heading p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 12px;
}
.ui-modal-footer {
  flex-shrink: 0;
  margin: 20px -24px -24px;
  padding: 16px 24px;
  border-top: 1px solid var(--border);
  background: var(--surface);
}
.config-modal--editor > .ui-modal-footer {
  margin: 0;
  padding: 18px 26px;
}
.config-modal--drawer {
  inset: 0 0 0 auto;
  transform: none;
  width: min(500px, 100vw);
  max-height: none;
  height: 100dvh;
  border-radius: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.config-modal--wide {
  width: min(1120px, calc(100vw - 48px));
  height: min(780px, calc(100dvh - 48px));
}
.config-modal--wide .config-modal-body {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
/* 居中编辑弹窗固定标题和底栏，长表单仅滚动中间字段区。 */
.config-modal--editor {
  width: min(680px, calc(100vw - 32px));
  padding: 0;
}
.config-modal--editor .config-modal-heading {
  margin: 0;
  padding: 22px 26px 20px;
  border-bottom: 1px solid var(--border);
}
.config-modal--editor .config-modal-body {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
@media (max-width: 540px) {
  .config-modal--editor .config-modal-heading {
    padding: 20px;
  }
}
.config-modal--drawer .config-modal-heading {
  flex-shrink: 0;
}
@media (max-width: 540px) {
  .config-modal--drawer {
    width: 100vw;
    padding: 20px 16px max(16px, env(safe-area-inset-bottom));
  }
}
</style>
