/** 组织授权跨层集成：真实身份、路由、目录与弹窗协作，网络按后端契约替换。 */
import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import App from '@/App.vue'
import { createAppRouter } from '@/router'
import { useAuthStore } from '@/features/auth/store'
import { useModelConfigStore } from '@/features/model-config/store'
import { authenticatedFetch } from '@/features/auth/authenticated'
import { createTestPinia } from '@tests/support/vitest/mount'
import { installMediaQuery } from '@tests/support/vitest/browser'
import { response } from '@tests/support/vitest/http'
import { authorizationData } from '@tests/support/data/authorization'
import { modelOptionsData } from '@tests/support/data/model-selection'

const fetchMock = vi.fn<typeof fetch>()
beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  installMediaQuery()
})

/** 建立指定身份并挂载完整应用，目录与模型选项使用独立响应，不发出真实请求。 */
async function open(identity = authorizationData().admin, path = '/organization') {
  const data = authorizationData(),
    pinia = createTestPinia(),
    auth = useAuthStore(pinia)
  fetchMock.mockResolvedValueOnce(response({ ...data.LOGIN, user: identity }))
  await auth.login(data.CREDENTIALS)
  fetchMock.mockImplementation(async (url) => {
    if (String(url) === '/api/auth/me') return response(auth.user)
    if (String(url).endsWith('/options')) return response(modelOptionsData())
    if (String(url).startsWith('/api/departments?'))
      return response({ items: [data.department], next_cursor: null })
    if (String(url).includes('/members?'))
      return response({
        items: [
          {
            ...data.member,
            ...(identity.roles.includes('department_admin')
              ? { id: identity.id, username: identity.username }
              : {}),
          },
        ],
        next_cursor: null,
      })
    return response({ items: [], next_cursor: null })
  })
  fetchMock.mockClear()
  const router = createAppRouter(createMemoryHistory())
  await router.push(path)
  await router.isReady()
  const page = mount(App, { attachTo: document.body, global: { plugins: [pinia, router] } })
  await flushPromises()
  return { page, router, auth, data }
}

it('普通账号通过兼容角色也不能进入模型或组织管理，两个聊天入口均隐藏', async () => {
  const { USER } = authorizationData()
  const { page, router } = await open({ ...USER, role: 'super_admin' })
  expect(router.currentRoute.value.name).toBe('chat')
  expect(page.find('a[href="/organization"]').exists()).toBe(false)
  expect(page.find('a[href="/models"]').exists()).toBe(false)
  await router.push('/models')
  await flushPromises()
  expect(router.currentRoute.value.name).toBe('chat')
  expect(fetchMock.mock.calls.some(([url]) => String(url).startsWith('/api/departments'))).toBe(
    false,
  )
})

it('超管从创建部门到加入成员使用正式表单，成功后重新读取身份和目录', async () => {
  const { page, data } = await open()
  expect(page.get('h1').text()).toBe('组织与权限')
  expect(page.get('[aria-label="管理范围"]').text()).toContain('全站组织与账号')
  expect(page.text()).toContain('管理权限不包含他人的个人会话')
  expect(page.text()).not.toContain('聚人成舟')
  expect(page.text()).not.toContain('归属清晰 · 权限有界')
  const body = new DOMWrapper(document.body)
  await page
    .findAll('button')
    .find((button) => button.text() === '新建部门')!
    .trigger('click')
  await flushPromises()
  await body.get('#management-input').setValue(' 新团队 ')
  fetchMock.mockResolvedValueOnce(response({ ...data.department, name: '新团队' }))
  await body.get('#management-action').trigger('submit')
  await flushPromises()
  expect(page.text()).not.toContain('操作已完成')
  expect(document.querySelector('#management-action')).toBeNull()
  expect(
    fetchMock.mock.calls.some(
      ([url, init]) => url === '/api/departments' && init?.body === '{"name":"新团队"}',
    ),
  ).toBe(true)
  expect(fetchMock.mock.calls.some(([url]) => url === '/api/auth/me')).toBe(true)
  await page
    .findAll('button')
    .find((button) => button.text() === '加入成员')!
    .trigger('click')
  await flushPromises()
  await body.get('#management-input').setValue('team_member')
  fetchMock.mockResolvedValueOnce(response(data.member))
  await body.get('#management-action').trigger('submit')
  await flushPromises()
  expect(page.text()).toContain(data.member.username)
})

it('本人移出部门后刷新授权，自动退出组织页并收回入口', async () => {
  const { departmentAdmin } = authorizationData()
  const { page, auth, router, data } = await open(departmentAdmin)
  fetchMock.mockImplementation(async (url, init) => {
    if (init?.method === 'DELETE') return response(null)
    if (url === '/api/auth/me') return response(data.USER)
    if (String(url).endsWith('/options')) return response(modelOptionsData())
    return response({ items: [], next_cursor: null })
  })
  await page
    .findAll('button')
    .find((button) => button.text() === '移出部门')!
    .trigger('click')
  await flushPromises()
  await new DOMWrapper(document.body).get('#management-action').trigger('submit')
  await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('chat'))
  await flushPromises()
  expect(auth.user?.grants).toEqual(data.USER.grants)
  expect(page.find('a[href="/organization"]').exists()).toBe(false)
})

it('403 重新确认身份并退出失权页面，同时清空模型管理缓存', async () => {
  const { router, auth, data } = await open()
  const config = useModelConfigStore()
  config.selectedProvider = 'previous-sensitive-configuration'
  fetchMock
    .mockResolvedValueOnce(response(null, 403, 40301, '没有权限'))
    .mockResolvedValueOnce(response(data.USER))
  await authenticatedFetch('/api/users')
  await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('chat'))
  expect(auth.isAuthenticated).toBe(true)
  expect(auth.notice).toContain('权限已发生变化')
  expect(config.selectedProvider).toBe('')
})

it('超管降为部门管理员仍保留组织入口，同时关闭全站表单并回到本部门视图', async () => {
  const { page, auth, router } = await open()
  await page
    .findAll('button')
    .find((button) => button.text() === '新建部门')!
    .trigger('click')
  await flushPromises()
  expect(document.querySelector('#management-action')).not.toBeNull()
  auth.user = authorizationData().departmentAdmin
  await flushPromises()
  expect(document.querySelector('#management-action')).toBeNull()
  expect(router.currentRoute.value.name).toBe('organization')
  expect(page.text()).toContain('权限已变化')
  expect(page.findAll('button').some((button) => button.text() === '全站账号')).toBe(false)
  expect(page.findAll('button').some((button) => button.text() === '加入成员')).toBe(true)
})

it('403 身份校验断网后收回权限，页面重试成功恢复入口且不重放写入', async () => {
  const { page, router, data } = await open()
  fetchMock
    .mockResolvedValueOnce(response(null, 403, 40301))
    .mockRejectedValueOnce(new TypeError('offline'))
  await authenticatedFetch('/api/users', { method: 'PUT' })
  await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('chat'))
  await flushPromises()
  expect(page.find('a[href="/organization"]').exists()).toBe(false)
  expect(page.text()).toContain('管理操作已暂停')
  fetchMock.mockResolvedValueOnce(response(data.admin))
  await page
    .findAll('button')
    .find((button) => button.text() === '重试权限校验')!
    .trigger('click')
  await flushPromises()
  expect(page.find('a[href="/organization"]').exists()).toBe(true)
  expect(page.findAll('button').some((button) => button.text() === '重试权限校验')).toBe(false)
  expect(
    fetchMock.mock.calls.filter(
      ([url, options]) => url === '/api/users' && options?.method === 'PUT',
    ),
  ).toHaveLength(1)
})
