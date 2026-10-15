<!-- 消息列表：限制阅读宽度，在会话变化后定位末尾；尺寸变化只跟随原本处于末尾的阅读位置。 -->
<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { ChatMessage } from '@/types/chat'
import MessageItem from './MessageItem.vue'

const props = defineProps<{ messages: ChatMessage[]; conversationId: string }>()
const end = ref<HTMLDivElement>()
const list = ref<HTMLDivElement>()
let observer: ResizeObserver | undefined
let scroller: HTMLElement | null = null
let followingEnd = true

/** DOM 更新后定位末尾；初次挂载以及消息变化时调用，尺寸变化由跟随状态决定。 */
async function scrollToEnd(): Promise<void> {
  await nextTick()
  end.value?.scrollIntoView?.({ block: 'end', behavior: 'instant' })
}

/** 记录用户是否在末尾阅读，调整窗口或展开代码块时不打断旧消息浏览。 */
function updateFollowing(): void {
  if (scroller)
    followingEnd = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 48
}

// 新会话和新消息始终展示末尾，独立于上一个会话的滚动位置。
watch(
  () => [props.conversationId, props.messages.length],
  () => {
    followingEnd = true
    scrollToEnd()
  },
  { immediate: true },
)

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
    <MessageItem v-for="message in messages" :key="message.id" :message="message" />
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
