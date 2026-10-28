/** 认证请求边界：验证请求头、取消、账号切换和统一响应，不访问真实服务。 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { authenticatedFetch, readEnvelope } from '../authenticated'
import { useAuthStore } from '../store'
import { createTestPinia } from '@tests/support/vitest/mount'
import { authenticate } from '@tests/support/vitest/auth'
import { createAuthData } from '@tests/support/data/auth'
import { deferredResponse, response } from '@tests/support/vitest/http'

const fetchMock = vi.fn<typeof fetch>()
// 仅替换网络；令牌取得、有效期和失效处理使用真实认证 store。
beforeEach(async () => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
  await authenticate(createTestPinia(), fetchMock)
})

describe('带身份的业务请求', () => {
  it('403 只刷新当前身份并保留失败响应，不重放原操作', async () => {
    const { USER } = createAuthData()
    fetchMock
      .mockResolvedValueOnce(response(null, 403, 40301, '权限变化'))
      .mockResolvedValueOnce(response(USER))
    const result = await authenticatedFetch('/api/example', { method: 'DELETE' })
    expect(result.status).toBe(403)
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(['/api/example', '/api/auth/me'])
    expect(useAuthStore().isAuthenticated).toBe(true)
  })

  it('403 后身份同步断网时收回旧授权但保留登录供重试', async () => {
    useAuthStore().user!.grants.push({
      permission: 'model:manage',
      scope_type: 'global',
      scope_id: null,
    })
    fetchMock
      .mockResolvedValueOnce(response(null, 403, 40301))
      .mockRejectedValueOnce(new TypeError('offline'))
    await authenticatedFetch('/api/example')
    expect(useAuthStore().can('model:manage')).toBe(false)
    expect(useAuthStore().isAuthenticated).toBe(true)
  })
  it('保留自定义请求头与取消信号，并覆盖调用方提供的旧 Bearer', async () => {
    const signal = new AbortController().signal
    fetchMock.mockResolvedValue(response(null))
    await authenticatedFetch('/api/example', {
      headers: { Accept: 'application/json', Authorization: 'Bearer old', 'X-Trace': 'case' },
      signal,
    })
    const options = fetchMock.mock.calls[0]![1]!
    const headers = new Headers(options.headers)
    expect(headers.get('Authorization')).toBe('Bearer test-access-token')
    expect(headers.get('Accept')).toBe('application/json')
    expect(headers.get('X-Trace')).toBe('case')
    expect(options.signal).toBe(signal)
  })

  it('无有效身份时不发送请求', async () => {
    useAuthStore().logout()
    await expect(authenticatedFetch('/api/example')).rejects.toMatchObject({ status: 401 })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('当前请求的 401 结束当前身份', async () => {
    fetchMock.mockResolvedValue(response(null, 401, 40101))
    await authenticatedFetch('/api/example')
    expect(useAuthStore().isAuthenticated).toBe(false)
  })

  it('旧令牌迟到的 401 不清除后来建立的新身份', async () => {
    const pending = deferredResponse()
    fetchMock.mockReturnValueOnce(pending.promise)
    const oldRequest = authenticatedFetch('/api/old')
    const { LOGIN, CREDENTIALS } = createAuthData()
    fetchMock.mockResolvedValueOnce(response({ ...LOGIN, access_token: 'new-token' }))
    await useAuthStore().login(CREDENTIALS)
    pending.resolve(response(null, 401, 40101))
    await oldRequest
    expect(useAuthStore().accessToken).toBe('new-token')
    expect(useAuthStore().isAuthenticated).toBe(true)
  })

  it('取消保留 AbortError，其他网络失败转换为安全说明', async () => {
    const controller = new AbortController()
    controller.abort()
    fetchMock.mockRejectedValue(new TypeError('private network detail'))
    await expect(
      authenticatedFetch('/api/example', { signal: controller.signal }),
    ).rejects.toMatchObject({ name: 'AbortError' })
    await expect(authenticatedFetch('/api/example')).rejects.toThrow('网络连接失败')
  })
})

describe('统一 JSON 响应', () => {
  it.each([null, {}, { code: 0.5 }, { code: 0 }])('拒绝不完整响应 %#', async (body) => {
    await expect(readEnvelope(new Response(JSON.stringify(body)))).rejects.toThrow('服务响应无效')
  })

  it('保留 HTTP 与业务状态，同时提供缺省错误说明', async () => {
    await expect(readEnvelope(response(null, 409, 40901, ''))).rejects.toMatchObject({
      status: 409,
      code: 40901,
      message: '请求失败，请稍后重试',
    })
    await expect(
      readEnvelope(new Response('<html>proxy error</html>', { status: 502 })),
    ).rejects.toMatchObject({ status: 502 })
    await expect(readEnvelope(response({ value: false }))).resolves.toEqual({ value: false })
  })
})
