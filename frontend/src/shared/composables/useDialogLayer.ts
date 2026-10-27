/** 弹层公共层级：通过 Vue 注入链为抽屉、编辑框和确认框分配相对层级，Portal 不打断归属。 */
import { inject, provide } from 'vue'

/** 登记当前弹层并返回遮罩和内容样式，保证子弹窗始终高于父弹层。
 * override 仅供外置业务宿主指定逻辑父层级；通常直接继承注入深度，打开后不跳层。
 */
export function useDialogLayer(override?: number) {
  const inherited = inject('zhizhou:modal-depth', 0)
  const depth = override ?? inherited
  provide('zhizhou:modal-depth', depth + 1)
  return {
    overlayStyle: depth ? { zIndex: `calc(var(--z-drawer) + ${depth * 2 - 1})` } : undefined,
    contentStyle: depth ? { zIndex: `calc(var(--z-drawer) + ${depth * 2})` } : undefined,
  }
}
