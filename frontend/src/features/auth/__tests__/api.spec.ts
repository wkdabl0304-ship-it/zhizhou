/** 认证接口契约测试：验证请求字段、Bearer 身份与统一响应校验，不访问真实服务。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthApiError, currentUser, login, register } from '../api'
import { CREDENTIALS, LOGIN, USER, response } from './helpers'

const fetchMock = vi.fn<typeof fetch>()
// 每个用例使用独立的网络替身，禁止意外请求真实认证服务。
beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})
// 清除全局替身，不影响已有聊天测试。
afterEach(() => vi.unstubAllGlobals())

describe('认证 HTTP 契约', () => {
  // 注册角色固定为普通用户，确认密码只属于页面，不进入接口。
  it('注册发送普通用户角色并返回公开身份', async () => {
    fetchMock.mockResolvedValue(response({ ...USER, created_at: '2026-10-22T10:00:00Z' }))
    expect(await register(CREDENTIALS)).toMatchObject(USER)
    expect(fetchMock).toHaveBeenCalledWith('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ ...CREDENTIALS, role: 'user' }),
    })
  })

  // 登录密码不经裁剪，身份恢复只发送令牌，不重复发送密码。
  it('登录取得令牌，再通过 Bearer 校验当前用户', async () => {
    fetchMock.mockResolvedValueOnce(response(LOGIN)).mockResolvedValueOnce(response(USER))
    expect(await login(CREDENTIALS)).toEqual(LOGIN)
    expect(JSON.parse(fetchMock.mock.calls[0]![1]!.body as string)).toEqual(CREDENTIALS)
    expect(await currentUser(LOGIN.access_token)).toEqual(USER)
    expect(fetchMock).toHaveBeenLastCalledWith('/api/auth/me', {
      method: 'GET',
      headers: { Accept: 'application/json', Authorization: `Bearer ${LOGIN.access_token}` },
    })
  })

  // HTTP 与业务码任一失败都不得建立登录，重名信息可供页面关联到用户名。
  it.each([
    [401, 40102, '用户名或密码错误'],
    [200, 20001, '用户名已存在'],
  ])('HTTP %i 业务码 %i 保留可展示的错误信息', async (status, code, message) => {
    fetchMock.mockResolvedValue(response(null, status, code, message))
    await expect(login(CREDENTIALS)).rejects.toMatchObject({
      name: 'AuthApiError',
      status,
      code,
      message,
    })
  })

  // 不信任服务端成功标记：令牌、类型、有效期与用户结构缺一不可。
  it.each([
    { ...LOGIN, access_token: '' },
    { ...LOGIN, token_type: 'basic' },
    { ...LOGIN, expires_in: 0 },
    { ...LOGIN, expires_in: 1.5 },
    { ...LOGIN, expires_in: Number.MAX_SAFE_INTEGER },
    { ...LOGIN, user: { ...USER, role: 'unknown' } },
    null,
  ])('拒绝损坏的登录数据 %#', async (data) => {
    fetchMock.mockResolvedValue(response(data))
    await expect(login(CREDENTIALS)).rejects.toThrow('登录响应格式无效')
  })

  // 错误代理页和底层网络堆栈不能作为身份数据，也不直接显示技术异常。
  it('无效 JSON 与网络异常转换成安全提示', async () => {
    fetchMock.mockResolvedValueOnce(new Response('<html>Bad gateway</html>', { status: 502 }))
    await expect(login(CREDENTIALS)).rejects.toThrow('服务响应无效')
    fetchMock.mockRejectedValueOnce(new TypeError('private internal network details'))
    await expect(login(CREDENTIALS)).rejects.toThrow('网络连接失败，请稍后重试')
  })

  // 其他认证接口也要验证公开身份结构，避免错误的成功响应进入页面。
  it('拒绝缺失业务码及不完整的注册、身份响应', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ data: LOGIN })))
    await expect(login(CREDENTIALS)).rejects.toBeInstanceOf(AuthApiError)
    fetchMock.mockResolvedValueOnce(response({ username: USER.username }))
    await expect(register(CREDENTIALS)).rejects.toThrow('注册响应格式无效')
    fetchMock.mockResolvedValueOnce(response(null))
    await expect(currentUser(LOGIN.access_token)).rejects.toThrow('身份响应格式无效')
  })

  // 页面取消后保留 AbortError 语义，供调用方忽略已离开的表单结果。
  it('向 fetch 传递取消信号并传播取消状态', async () => {
    const controller = new AbortController()
    controller.abort()
    fetchMock.mockRejectedValue(new DOMException('aborted', 'AbortError'))
    await expect(login(CREDENTIALS, controller.signal)).rejects.toMatchObject({
      name: 'AbortError',
    })
    expect(fetchMock.mock.calls[0]![1]?.signal).toBe(controller.signal)
  })
})
