/** 授权规则回归：入口必须按操作与范围判定，不使用旧兼容角色推导权限。 */
import { expect, it } from 'vitest'
import { authorizationData } from '@tests/support/data/authorization'
import { hasGrant, canManageOrganization } from '../permissions'

it('兼容角色和角色列表都不能替代有效授权', () => {
  const { USER, admin } = authorizationData()
  expect(hasGrant({ ...USER, role: 'super_admin', roles: ['super_admin'] }, 'model:manage')).toBe(
    false,
  )
  expect(hasGrant(admin, 'model:manage')).toBe(true)
  expect(hasGrant(admin, 'conversation:read', 'other-user')).toBe(false)
  expect(canManageOrganization(USER)).toBe(false)
  expect(canManageOrganization(admin)).toBe(true)
  expect(hasGrant(null, 'model:manage')).toBe(false)
})

it('部门授权只允许本人当前部门的对应操作，错误绑定与其他操作均不匹配', () => {
  const { departmentAdmin: user, department } = authorizationData()
  expect(canManageOrganization(user)).toBe(true)
  expect(hasGrant(user, 'department_member:add', department.id)).toBe(true)
  expect(hasGrant(user, 'department_member:add', 'other-department')).toBe(false)
  expect(hasGrant(user, 'department_member:add')).toBe(false)
  expect(hasGrant(user, 'role:assign', department.id)).toBe(false)
  expect(hasGrant({ ...user, department: null }, 'department_member:add', department.id)).toBe(
    false,
  )
  expect(
    hasGrant(
      {
        ...user,
        grants: [{ permission: 'conversation:read', scope_type: 'self', scope_id: user.id }],
      },
      'conversation:read',
      user.id,
    ),
  ).toBe(true)
})
