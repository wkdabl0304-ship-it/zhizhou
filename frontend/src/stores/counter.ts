/**
 * Pinia 状态管理示例：演示可写状态、派生状态和修改状态的 action。
 * 计数器尚未接入聊天业务，也没有持久化到浏览器或后端。
 */
import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

/** 获取或创建 counter store，供组件读取 count、doubleCount 并调用 increment。 */
export const useCounterStore = defineStore('counter', () => {
  // Setup store 工厂：由 Pinia 按 store 标识管理实例，返回需要向组件暴露的成员。
  const count = ref(0)
  // 派生值在 count 改变后自动更新；计算回调只读取状态，不修改源数据。
  const doubleCount = computed(() => count.value * 2)
  /** 将计数增加一；组件通过该 action 修改状态，无额外参数或返回值。 */
  function increment() {
    count.value++
  }

  // 只有返回的状态与 action 才构成 store 的公开接口。
  return { count, doubleCount, increment }
})
