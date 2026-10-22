/** 通用动效生命周期：减少动态效果和页面可见性分别控制，偏好只保存在当前组件内存中。 */
import { computed, onBeforeUnmount, ref } from 'vue'
import { useMediaQuery } from './useMediaQuery'
/**
 * 为组件提供是否播放动效及是否暂停后台动画的响应式状态。
 * 返回组件内的请求开关、系统减少动态效果偏好、页面可见性和最终启用状态；
 * 页面通过数据属性控制 CSS 动画，本函数在卸载时解除可见性监听。
 */
export function useMotionPreference() {
  const requested = ref(true)
  const reduced = useMediaQuery('(prefers-reduced-motion: reduce)')
  const visible = ref(document.visibilityState !== 'hidden')
  // 后台暂停而不重置入场状态，关闭或系统减少动态效果时展示完整静态画面。
  const enabled = computed(() => requested.value && !reduced.value)
  /** 同步当前文档可见性，不启动持续的 JS 渲染循环。 */
  function updateVisibility(): void {
    visible.value = document.visibilityState !== 'hidden'
  }
  document.addEventListener('visibilitychange', updateVisibility)
  // 解除监听，避免离开聊天页或预览页后仍持有组件状态。
  onBeforeUnmount(() => document.removeEventListener('visibilitychange', updateVisibility))
  return { requested, reduced, visible, enabled }
}
