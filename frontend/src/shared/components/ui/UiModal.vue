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
import { inject, nextTick, onUnmounted, provide } from 'vue'
import UiIconButton from './UiIconButton.vue'
const props = defineProps<{
  open: boolean
  title: string
  description: string
  drawer?: boolean
  wide?: boolean
  editor?: boolean
  returnFocus?: HTMLElement | null
  closeDisabled?: boolean
}>()
const emit = defineEmits<{ 'update:open': [value: boolean] }>()
// Portal 保留 Vue 的注入链；每层遮罩必须高于上一层内容，确认框才能覆盖编辑弹窗。
const depth = inject('zhizhou:modal-depth', 0)
provide('zhizhou:modal-depth', depth + 1)
const overlayStyle = depth ? { zIndex: `calc(var(--z-drawer) + ${depth * 2 - 1})` } : undefined
const contentStyle = depth ? { zIndex: `calc(var(--z-drawer) + ${depth * 2})` } : undefined
// 编辑开始会禁用原卡片按钮；调用方可提前保存触发器，避免浏览器清空焦点后丢失返回位置。
const previous = props.returnFocus ?? document.activeElement
/** 模态关闭后恢复触发元素；列表重绘移除触发器时回到页面标题。 */
function restoreFocus(event: Event): void {
  event.preventDefault()
  restoreTarget()
}
/** 在焦点约束已释放后恢复仍存在的入口，避免嵌套弹层卸载互相抢焦点。 */
function restoreTarget(): void {
  if (previous instanceof HTMLElement && previous.isConnected) previous.focus()
  else {
    // 编辑器与放弃确认可能同帧卸载；确认层不能把已恢复到主面板的焦点再次移到页面外。
    const dialogs = document.querySelectorAll<HTMLElement>('.config-modal[data-state="open"]')
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
  void nextTick(() => {
    setTimeout(restoreTarget, 0)
  })
})
</script>
<template>
  <DialogRoot :open="open" @update:open="emit('update:open', $event)">
    <DialogPortal>
      <DialogOverlay class="config-modal-overlay" :style="overlayStyle" />
      <DialogContent
        class="config-modal"
        :class="{
          'config-modal--drawer': drawer,
          'config-modal--wide': wide,
          'config-modal--editor': editor,
        }"
        :style="contentStyle"
        @close-auto-focus="restoreFocus"
      >
        <header class="config-modal-heading">
          <div>
            <DialogTitle>{{ title }}</DialogTitle
            ><DialogDescription>{{ description }}</DialogDescription>
          </div>
          <UiIconButton label="关闭" :disabled="closeDisabled" @click="emit('update:open', false)"
            ><X :size="18"
          /></UiIconButton>
        </header>
        <div class="config-modal-body"><slot /></div>
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
