<!-- 消息列表：限制阅读宽度，在会话变化后定位末尾；尺寸变化只跟随原本处于末尾的阅读位置。 -->
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { ChatMessage } from '@/features/chat/types'
import MessageItem from './MessageItem.vue'
import ModelChangeNotice from './ModelChangeNotice.vue'
import type { ModelIdentity } from '@/features/model-selection/types'

const props = defineProps<{
  messages: ChatMessage[]
  conversationId: string
}>()
// 只比较已经开始输出的轮次；未发送、等待 start 或尚无模型输出时不展示分界线。
const timeline = computed(() => {
  let previous: ModelIdentity | null = null
  const items = props.messages.map((message) => {
    const change =
      message.role === 'user' &&
      message.modelReplyStarted !== false &&
      previous &&
      message.model &&
      previous.catalog_model_id !== message.model.catalog_model_id
        ? { from: previous, to: message.model }
        : null
    if (message.role === 'user' && message.modelReplyStarted !== false)
      previous = message.model ?? null
    return { message, change }
  })
  return items
})
const end = ref<HTMLDivElement>()
const list = ref<HTMLDivElement>()
let observer: ResizeObserver | undefined
let scroller: HTMLElement | null = null
let followingEnd = true

/** 将消息列表滚动到最新内容；等待 DOM 更新后定位末尾，供挂载、消息和尺寸变化调用。 */
async function scrollToEnd(): Promise<void> {
  await nextTick()
  end.value?.scrollIntoView?.({ block: 'end', behavior: 'instant' })
}

/** 更新列表是否应跟随最新消息的状态；距底部不足 48px 时视为正在末尾阅读。 */
function updateFollowing(): void {
  if (scroller)
    followingEnd = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 48
}

// 新会话或新消息显示末尾；向前分页则以高度差保持原阅读位置，不跳到最新消息。
watch(
  () => [props.conversationId, props.messages.length, props.messages[0]?.id] as const,
  async (value, previous) => {
    if (
      previous &&
      value[0] === previous[0] &&
      value[1] > previous[1] &&
      previous[2] &&
      value[2] !== previous[2] &&
      scroller
    ) {
      const target = scroller
      const top = target.scrollTop
      const height = target.scrollHeight
      followingEnd = false
      await nextTick()
      if (props.conversationId === value[0]) target.scrollTop = top + target.scrollHeight - height
      return
    }
    followingEnd = true
    await scrollToEnd()
  },
  { immediate: true },
)

// 挂载后接入滚动监听和尺寸观察，让已在末尾的用户持续看到新增内容。
onMounted(() => {
  scroller = list.value?.parentElement ?? null
  scroller?.addEventListener('scroll', updateFollowing, { passive: true })
  if (typeof ResizeObserver === 'undefined') return
  // 内容重新换行或主区域变高时，原本处于末尾的用户继续看到最后一条消息。
  observer = new ResizeObserver(() => {
    if (followingEnd) scrollToEnd()
  })
  if (list.value) observer.observe(list.value)
  if (scroller) observer.observe(scroller)
})

// 列表随页面卸载时释放监听和观察器，不保留旧会话的 DOM 引用。
onBeforeUnmount(() => {
  scroller?.removeEventListener('scroll', updateFollowing)
  observer?.disconnect()
})
</script>

<template>
  <div ref="list" class="message-list">
    <template v-for="item in timeline" :key="item.message.id">
      <ModelChangeNotice v-if="item.change" :from="item.change.from" :to="item.change.to" />
      <MessageItem :message="item.message" />
    </template>
    <div ref="end" class="message-end" aria-hidden="true" />
  </div>
</template>

<style scoped>
.message-list {
  max-width: var(--content-width);
  margin: 0 auto;
  padding-bottom: 4px;
}
.message-end {
  height: 1px;
}
</style>
