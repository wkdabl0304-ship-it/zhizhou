<!-- 通用模态框：以 Reka 管理 Portal、焦点、Esc 和滚动锁，可切换为右侧表单抽屉。 -->
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
import { nextTick, onUnmounted } from 'vue'
import UiIconButton from './UiIconButton.vue'
defineProps<{ open: boolean; title: string; description: string; drawer?: boolean }>()
const emit = defineEmits<{ 'update:open': [value: boolean] }>()
const previous = document.activeElement
/** 模态关闭后恢复触发元素；列表重绘移除触发器时回到页面标题。 */
function restoreFocus(event: Event): void {
  event.preventDefault()
  restoreTarget()
}
/** 在焦点约束已释放后恢复仍存在的入口，避免嵌套弹层卸载互相抢焦点。 */
function restoreTarget(): void {
  if (previous instanceof HTMLElement && previous.isConnected) previous.focus()
  else {
    // 嵌套确认框与抽屉可能在同一帧卸载，不覆盖另一层已经恢复的页面焦点。
    const active = document.activeElement
    if (
      active instanceof HTMLElement &&
      active !== document.body &&
      !active.closest('[role="dialog"]')
    )
      return
    document.querySelector<HTMLElement>('main h1[tabindex]')?.focus()
  }
}
// 页面使用 v-if 移除整个 DialogRoot 时，内部事件可能随祖先卸载而停止转发。
// 等待 DOM 卸载完成后补充同一恢复动作；仍有上层弹窗时交给其焦点约束管理。
onUnmounted(() => {
  void nextTick(() => {
    if (!document.querySelector('.config-modal[data-state="open"]')) restoreTarget()
  })
})
</script>
<template>
  <DialogRoot :open="open" @update:open="emit('update:open', $event)">
    <DialogPortal>
      <DialogOverlay class="config-modal-overlay" />
      <DialogContent
        class="config-modal"
        :class="{ 'config-modal--drawer': drawer }"
        @close-auto-focus="restoreFocus"
      >
        <header class="config-modal-heading">
          <div>
            <DialogTitle>{{ title }}</DialogTitle
            ><DialogDescription>{{ description }}</DialogDescription>
          </div>
          <UiIconButton label="关闭" @click="emit('update:open', false)"
            ><X :size="18"
          /></UiIconButton>
        </header>
        <slot />
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
  overflow: auto;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-lg);
  background: var(--surface);
  color: var(--text);
  box-shadow: var(--shadow-popover);
  padding: 24px;
}
.config-modal-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 20px;
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
