/** 响应式媒体查询：监听浏览器断点，并在组件销毁时释放监听。 */
import { onBeforeUnmount, ref } from 'vue'

/**
 * 将浏览器媒体查询转换为可供 Vue 组件使用的响应式匹配状态。
 * query 为 matchMedia 查询字符串，返回布尔 ref；监听 change 更新状态，
 * 并在组件卸载时解除监听，适合用于窄屏导航等断点判断。
 */
export function useMediaQuery(query: string) {
  const media = window.matchMedia(query)
  const matches = ref(media.matches)

  /** 将浏览器断点变化同步到 Vue 状态。 */
  function update(event: MediaQueryListEvent): void {
    matches.value = event.matches
  }

  media.addEventListener('change', update)
  // 组件离开后不再接收断点事件，避免重复挂载带来的监听泄漏。
  onBeforeUnmount(() => media.removeEventListener('change', update))
  return matches
}
