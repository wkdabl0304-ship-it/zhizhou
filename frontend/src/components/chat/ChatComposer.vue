<!-- 聊天输入区：负责发送规则、输入法组合保护与原生表单语义，不负责生成回复。 -->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowUp, CornerDownLeft, Sparkles } from '@lucide/vue'
import UiAutoTextarea from '@/components/ui/UiAutoTextarea.vue'
import UiIconButton from '@/components/ui/UiIconButton.vue'
import UiTooltip from '@/components/ui/UiTooltip.vue'

const model = defineModel<string>({ default: '' })
const props = defineProps<{ disabled?: boolean; sending?: boolean }>()
const emit = defineEmits<{ send: [text: string] }>()
const input = ref<InstanceType<typeof UiAutoTextarea>>()
const composing = ref(false)
// 等待回复时允许继续编辑草稿，但阻止再次提交，避免同一 thread_id 并发续写历史。
const canSend = computed(
  () => !props.disabled && !props.sending && !composing.value && Boolean(model.value.trim()),
)

/** 同步交出当前内容；业务层接收后由该输入区清空草稿。 */
function submit(): void {
  if (!canSend.value) return
  emit('send', model.value.trim())
  model.value = ''
  input.value?.focus()
}

/** Enter 发送；组合输入、兼容性 keyCode 229 和 Shift 换行均交还输入法/浏览器。 */
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

/** 供首页建议按钮在填入草稿后将焦点送回文本框。 */
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
      <span class="composer-mode"><Sparkles :size="15" /><span>一起探索，慢慢理清</span></span>
      <div class="composer-send">
        <span class="composer-key-hint"><CornerDownLeft :size="12" />发送</span
        ><UiTooltip text="发送消息"
          ><UiIconButton type="submit" class="send-button" label="发送消息" :disabled="!canSend"
            ><ArrowUp :size="19" /></UiIconButton
        ></UiTooltip>
      </div>
    </div>
  </form>
</template>

<style scoped>
.chat-composer {
  padding: 19px 18px 12px;
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
  gap: 12px;
  margin-top: 17px;
}
.composer-mode {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--text-muted);
  font-size: 11px;
}
.composer-mode svg {
  color: var(--brand);
}
.composer-send {
  display: flex;
  align-items: center;
  gap: 13px;
}
.composer-key-hint {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  color: var(--text-muted);
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
    padding: 16px 15px 10px;
    border-radius: 20px;
  }
  .composer-key-hint {
    display: none;
  }
}
@media (pointer: coarse) {
  .send-button {
    width: 44px;
    height: 44px;
  }
}
</style>
