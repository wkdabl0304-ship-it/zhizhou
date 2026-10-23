/** 公共支撑回归：验证数据和响应独立，以及状态容器清理确实停止副作用。 */
import { describe, expect, it, vi } from 'vitest'
import { defineStore } from 'pinia'
import { onScopeDispose } from 'vue'
import { createAuthData } from '../data/auth'
import { info, turn } from '../data/chat'
import { response, deferredResponse } from '../vitest/http'
import { controlledStream } from '../vitest/sse'
import { success } from '../vitest/chat'
import { createTestPinia, disposeTestPinia } from '../vitest/mount'

describe('独立测试资源', () => {
  it('工厂不共享身份、目录或轮次中的可变数据', () => {
    const first = createAuthData()
    first.USER.username = 'changed'
    first.LOGIN.user.username = 'another'
    expect(createAuthData().USER.username).toBe('lin_zhou')
    expect(info()).not.toBe(info())
    expect(turn().public_events).not.toBe(turn().public_events)
  })

  it('每次返回可独立消费的响应，并能显式推进迟到请求', async () => {
    expect(await response(false).json()).toMatchObject({ code: 0, data: false })
    const pending = deferredResponse()
    pending.resolve(response('ready'))
    expect(await (await pending.promise).json()).toMatchObject({ data: 'ready' })
    const first = await success('conversation').text()
    const second = await success('conversation').text()
    expect(first).not.toBe(second)
  })

  it('消费者取消可控流后，关闭支撑不再重复操作底层控制器', async () => {
    const stream = controlledStream()
    await stream.response.body!.cancel()
    expect(stream.isCancelled()).toBe(true)
    expect(() => stream.close()).not.toThrow()
  })

  it('统一清理停止状态作用域，重复清理保持幂等', () => {
    const stopped = vi.fn<() => void>()
    // 资源替身通过真实 Pinia 作用域登记清理，不依赖私有容器字段。
    const useResource = defineStore('test-resource', () => {
      onScopeDispose(stopped)
      return {}
    })
    useResource(createTestPinia())
    disposeTestPinia()
    disposeTestPinia()
    expect(stopped).toHaveBeenCalledOnce()
  })
})
