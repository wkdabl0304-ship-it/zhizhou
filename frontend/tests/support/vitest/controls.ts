/** 表单控件测试支撑：通过实际键盘事件选择 Portal 选项，不直接改组件私有状态。 */
import { afterEach, vi } from 'vitest'
import { DOMWrapper, flushPromises } from '@vue/test-utils'
const scrollDescriptor = Object.getOwnPropertyDescriptor(Element.prototype, 'scrollIntoView')

/** 安装 jsdom 缺少的聚焦滚动方法；不伪造布局或浮层定位结果。 */
export function installSelectBrowser(): void {
  if (!Element.prototype.scrollIntoView)
    Object.defineProperty(Element.prototype, 'scrollIntoView', {
      configurable: true,
      value: vi.fn<() => void>(),
    })
}
// 收尾恢复原始浏览器能力，避免当前控件测试影响其他模块。
afterEach(() => {
  if (scrollDescriptor) Object.defineProperty(Element.prototype, 'scrollIntoView', scrollDescriptor)
  else Reflect.deleteProperty(Element.prototype, 'scrollIntoView')
})

/** 打开单选框并按业务值确认选项，保留第三方焦点与键盘处理。 */
export async function chooseSelect(
  trigger: Pick<DOMWrapper<Element>, 'trigger'>,
  value: string,
): Promise<void> {
  installSelectBrowser()
  await trigger.trigger('keydown', { key: 'ArrowDown' })
  await flushPromises()
  const option = new DOMWrapper(document.body)
    .findAll('[role="option"]')
    .find((row) => row.attributes('data-value') === value)
  if (!option) throw new Error(`没有找到下拉选项：${value}`)
  await option.trigger('keydown', { key: 'Enter' })
  await flushPromises()
}
