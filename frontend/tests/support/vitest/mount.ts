/** 测试资源注册：为各例创建独立 Pinia，并在统一收尾时停止状态层副作用。 */
import { createPinia, disposePinia, type Pinia } from 'pinia'
const instances = new Set<Pinia>()

/** 创建并登记独立状态容器；调用方可提前销毁，统一收尾保证遗漏资源也被释放。 */
export function createTestPinia(): Pinia {
  const pinia = createPinia()
  instances.add(pinia)
  return pinia
}

/** 停止本例登记的全部状态容器，清理定时器、监听和在途请求后清空登记表。 */
export function disposeTestPinia(): void {
  for (const pinia of instances) disposePinia(pinia)
  instances.clear()
}
