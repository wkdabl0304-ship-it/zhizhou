<!-- 聊天输入区：负责发送规则、输入法组合保护与原生表单语义，不负责生成回复。 -->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowUp } from '@lucide/vue'
import UiAutoTextarea from '@/shared/components/ui/UiAutoTextarea.vue'
import UiIconButton from '@/shared/components/ui/UiIconButton.vue'
import UiTooltip from '@/shared/components/ui/UiTooltip.vue'

const model = defineModel<string>({ default: '' })
const props = defineProps<{ disabled?: boolean; sending?: boolean; sendBlocked?: boolean }>()
const emit = defineEmits<{ send: [text: string] }>()
const input = ref<InstanceType<typeof UiAutoTextarea>>()
const composing = ref(false)
// 等待回复时允许继续编辑草稿，但阻止再次提交，避免同一业务会话并发续写历史。
const canSend = computed(
  () =>
    !props.disabled &&
    !props.sending &&
    !props.sendBlocked &&
    !composing.value &&
    Boolean(model.value.trim()),
)

/**
 * 提交当前输入，通知父页面开始发送聊天。
 * 仅在 canSend 允许时交出正文并聚焦输入框；父级业务接受发送后才清空草稿，
 * 发送前可能需要确认，组件不能先丢弃用户输入。
 */
function submit(): void {
  if (!canSend.value) return
  emit('send', model.value.trim())
  input.value?.focus()
}

/**
 * 处理输入区的 Enter 快捷发送，避免误发中文输入法确认或换行操作。
 * 普通 Enter 阻止默认换行并调用 submit；Shift、组合输入及兼容性 keyCode 229
 * 交还输入法或浏览器处理，其他按键不干预。
 */
function onKeydown(event: KeyboardEvent): void {
  if (
    event.key !== 'Enter' ||
    event.shiftKey ||
    event.isComposing ||
    composing.value ||
    event.keyCode === 229
  )
    return
  event.preventDefault()
  submit()
}

/** 将焦点移回内部文本框，供父页面恢复连续输入。 */
function focus(): void {
  input.value?.focus()
}

defineExpose({ focus })
</script>

<template>
  <form
    class="chat-composer"
    :class="{ 'is-disabled': disabled }"
    aria-label="发送消息"
    :aria-busy="sending"
    @submit.prevent="submit"
  >
    <UiAutoTextarea
      ref="input"
      v-model="model"
      label="消息内容"
      placeholder="有什么想法，和知舟聊聊"
      :disabled="disabled"
      @keydown="onKeydown"
      @compositionstart="composing = true"
      @compositionend="composing = false"
    />
    <div class="composer-toolbar">
      <div class="composer-reasoning"><slot name="reasoning-controls" /></div>
      <div class="composer-send">
        <slot name="model-selector" />
        <UiTooltip text="发送消息"
          ><UiIconButton type="submit" class="send-button" label="发送消息" :disabled="!canSend"
            ><ArrowUp :size="19" /></UiIconButton
        ></UiTooltip>
      </div>
    </div>
  </form>
</template>

<style scoped>
.chat-composer {
  padding: 16px 16px 10px;
  border: 1px solid var(--border-strong);
  border-radius: 20px;
  background: var(--surface);
  box-shadow: var(--shadow-composer);
  transition: border-color var(--duration-fast);
}
.chat-composer:focus-within {
  border-color: var(--brand);
}
.chat-composer.is-disabled {
  opacity: 0.6;
}
.composer-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 12px;
}
.chat-composer :deep(.ui-textarea) {
  min-height: 68px;
  max-height: 260px;
}
.composer-reasoning {
  min-width: 0;
}
.composer-send {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  margin-left: auto;
}
.send-button {
  width: 33px;
  height: 33px;
  border-radius: 50%;
  background: var(--action);
  color: var(--action-contrast);
}
.send-button:hover:not(:disabled) {
  background: var(--brand);
  color: var(--brand-contrast);
}
.send-button:disabled {
  opacity: 1;
  background: var(--surface-hover);
  color: var(--text-muted);
}
@media (max-width: 760px) {
  .chat-composer {
    padding: 14px 14px 10px;
    border-radius: 20px;
  }
  .composer-toolbar {
    flex-wrap: wrap;
  }
}
@media (pointer: coarse) {
  .send-button {
    width: 44px;
    height: 44px;
  }
}
</style>
