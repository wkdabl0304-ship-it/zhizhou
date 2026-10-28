import { chooseSelect } from '@tests/support/vitest/controls'
/** 组织组件行为测试：验证字段校验、目标确认、失败恢复、部门范围与目录操作入口。 */
import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import { TooltipProvider } from 'reka-ui'
import { beforeEach, expect, it, vi } from 'vitest'
import { createTestPinia } from '@tests/support/vitest/mount'
import { authenticate } from '@tests/support/vitest/auth'
import { deferredResponse, response } from '@tests/support/vitest/http'
import { authorizationData } from '@tests/support/data/authorization'
import { useAuthStore } from '@/features/auth/store'
import ManagementDialog from '../components/ManagementDialog.vue'
import DepartmentDirectory from '../components/DepartmentDirectory.vue'
import UserDirectory from '../components/UserDirectory.vue'
import type { ManagementAction } from '../types'

const fetchMock = vi.fn<typeof fetch>()
beforeEach(async () => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  await authenticate(createTestPinia(), fetchMock)
  useAuthStore().user = authorizationData().admin
})

/** 挂载真实公共弹窗与操作表单，Portal 直接检查用户可见 DOM。 */
async function dialog(action: ManagementAction) {
  const wrapper = mount(ManagementDialog, { props: { action }, attachTo: document.body })
  await flushPromises()
  return { wrapper, body: new DOMWrapper(document.body) }
}

it('空白部门名不请求后端，保存时固定部门目标并阻止重复提交', async () => {
  const { department } = authorizationData(),
    pending = deferredResponse()
  fetchMock.mockReturnValue(pending.promise)
  const { wrapper, body } = await dialog({ kind: 'rename-department', department })
  await body.get('input').setValue('   ')
  await body.get('form').trigger('submit')
  expect(fetchMock).not.toHaveBeenCalled()
  expect(body.text()).toContain('部门名称须为')
  await body.get('input').setValue(' 云帆团队 ')
  await body.get('form').trigger('submit')
  await body.get('form').trigger('submit')
  expect(fetchMock).toHaveBeenCalledTimes(1)
  expect(body.get('input').attributes('disabled')).toBeDefined()
  pending.resolve(response({ ...department, name: '云帆团队' }))
  await flushPromises()
  expect(wrapper.emitted('saved')).toHaveLength(1)
})

it('密码原样提交，失败清空敏感值并允许重试', async () => {
  const { managedUser: user } = authorizationData()
  fetchMock.mockResolvedValue(response(null, 409, 40907, '账号状态已变化'))
  const { wrapper, body } = await dialog({ kind: 'reset-password', user })
  expect(body.text()).toContain('全部旧令牌失效')
  await body.get('input').setValue(' secret password ')
  await body.get('form').trigger('submit')
  await flushPromises()
  expect(JSON.parse(String(fetchMock.mock.calls[0]![1]?.body))).toEqual({
    password: ' secret password ',
  })
  expect((body.get('input').element as HTMLInputElement).value).toBe('')
  expect(body.text()).toContain('账号状态已变化')
  expect(wrapper.emitted('conflict')).toHaveLength(1)
  expect(wrapper.emitted('saved')).toBeUndefined()
})

it('删除与最后超管冲突保留确认弹窗，不伪报成功', async () => {
  const { managedUser: user } = authorizationData()
  fetchMock.mockResolvedValue(response(null, 409, 40906, '必须保留至少一名可用超管'))
  const { wrapper, body } = await dialog({ kind: 'revoke-super-admin', user })
  expect(body.text()).toContain(user.username)
  await body.get('form').trigger('submit')
  await flushPromises()
  expect(body.text()).toContain('必须保留至少一名可用超管')
  expect(wrapper.emitted('saved')).toBeUndefined()
})

it('密码按 Unicode 字符校验长度，不把四个双码元字符当作八位密码', async () => {
  const { managedUser: user } = authorizationData()
  const { body } = await dialog({ kind: 'reset-password', user })
  await body.get('input').setValue('🌊🌊🌊🌊')
  await body.get('form').trigger('submit')
  expect(fetchMock).not.toHaveBeenCalled()
  expect(body.text()).toContain('密码长度须为')
})

it('全局管理员离开部门保留全局身份，确认说明不误称其会失去管理权限', async () => {
  const { admin, department } = authorizationData()
  useAuthStore().user = admin
  const { body } = await dialog({
    kind: 'remove-member',
    department,
    member: { id: admin.id, username: admin.username, is_active: true, roles: [] },
  })
  expect(body.text()).toContain('全局角色和个人内容保留')
  expect(body.text()).not.toContain('并返回聊天')
})

it('表单打开后失去写权限时拒绝发送旧目标操作', async () => {
  const { managedUser: user } = authorizationData()
  const { body } = await dialog({ kind: 'reset-password', user })
  await body.get('input').setValue('safe-password')
  useAuthStore().user = authorizationData().departmentAdmin
  await body.get('form').trigger('submit')
  expect(fetchMock).not.toHaveBeenCalled()
  expect(body.text()).toContain('当前权限已变化')
})

it('部门管理员仅加载本部门成员，提供加入和移出但无角色及全站管理操作', async () => {
  const { departmentAdmin, department, member } = authorizationData()
  useAuthStore().user = departmentAdmin
  fetchMock.mockImplementation(async (url) =>
    response({
      items: String(url).includes('/members?') ? [member] : [department],
      next_cursor: null,
    }),
  )
  const wrapper = mount(DepartmentDirectory, { global: { components: { TooltipProvider } } })
  await flushPromises()
  expect(wrapper.text()).toContain(member.username)
  expect(wrapper.text()).not.toContain('新建部门')
  expect(wrapper.text()).not.toContain('设为管理员')
  const add = wrapper.findAll('button').find((button) => button.text() === '加入成员')!
  await add.trigger('click')
  expect(wrapper.emitted('action')?.[0]).toEqual([{ kind: 'add-member', department }])
  expect(fetchMock.mock.calls.some(([url]) => String(url).startsWith('/api/users'))).toBe(false)
})

it('账号筛选明确传递停用与无部门条件，停用账号不显示授予角色入口', async () => {
  const { admin, managedUser, department } = authorizationData()
  useAuthStore().user = admin
  fetchMock.mockImplementation(async (url) =>
    response({
      items: String(url).startsWith('/api/departments')
        ? [department]
        : [{ ...managedUser, is_active: false }],
      next_cursor: null,
    }),
  )
  const wrapper = mount(UserDirectory, { attachTo: document.body })
  await flushPromises()
  await chooseSelect(wrapper.get('[role="combobox"][aria-label="账号状态"]'), 'false')
  await wrapper.get('input[type="checkbox"]').setValue(true)
  await wrapper.get('input[type="search"]').setValue('team')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(fetchMock.mock.calls.at(-1)?.[0]).toBe(
    '/api/users?limit=20&search=team&is_active=false&unassigned=true',
  )
  expect(wrapper.text()).toContain('启用')
  expect(wrapper.text()).not.toContain('授予超管')
})

it('按具体部门筛选账号，并在勾选无部门时清除互斥条件', async () => {
  const { admin, managedUser, department } = authorizationData()
  useAuthStore().user = admin
  fetchMock.mockImplementation(async (url) =>
    response({
      items: String(url).startsWith('/api/departments') ? [department] : [managedUser],
      next_cursor: null,
    }),
  )
  const wrapper = mount(UserDirectory, { attachTo: document.body })
  await flushPromises()
  await chooseSelect(wrapper.get('[role="combobox"][aria-label="所属部门"]'), department.id)
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(fetchMock.mock.calls.at(-1)?.[0]).toBe(
    `/api/users?limit=20&department_id=${department.id}`,
  )
  await wrapper.get('input[type="checkbox"]').setValue(true)
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(fetchMock.mock.calls.at(-1)?.[0]).toBe('/api/users?limit=20&unassigned=true')
  expect(
    wrapper.get('[role="combobox"][aria-label="所属部门"]').attributes('disabled'),
  ).toBeDefined()
})
