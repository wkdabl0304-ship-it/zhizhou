/** 响应式媒体查询：监听浏览器断点，并在组件销毁时释放监听。 */
import { onBeforeUnmount, ref } from 'vue'

/** 返回查询匹配状态；用于窄屏抽屉切换，不以 UA 推断设备种类。 */
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
