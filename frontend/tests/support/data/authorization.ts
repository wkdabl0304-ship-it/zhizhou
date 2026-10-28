/** 组织管理契约工厂：独立构造全局管理员、本部门管理员与公开目录，不包含真实凭据。 */
import { createAuthData } from './auth'
import type { Department, ManagedUser, Member } from '@/features/authorization/types'

/** 返回一次测试独立持有的身份、部门和成员对象。 */
export function authorizationData() {
  const { USER, LOGIN, CREDENTIALS } = createAuthData()
  const department: Department = {
    id: '22222222-2222-4222-8222-222222222222',
    name: '山海研发部',
    created_at: '2026-10-28T00:00:00Z',
    updated_at: '2026-10-28T00:00:00Z',
  }
  const member: Member = {
    id: '33333333-3333-4333-8333-333333333333',
    username: 'team_member',
    is_active: true,
    roles: [],
  }
  const managedUser: ManagedUser = {
    ...member,
    department: null,
    roles: ['user'],
    created_at: department.created_at,
    updated_at: department.updated_at,
  }
  const admin = {
    ...USER,
    roles: ['user', 'super_admin'],
    grants: [
      ...USER.grants,
      ...[
        'model:manage',
        'user:read',
        'user:set_active',
        'user:reset_password',
        'department:read',
        'department:create',
        'department:update',
        'department:delete',
        'department_member:read',
        'department_member:add',
        'department_member:remove',
        'role:assign',
        'role:revoke',
      ].map((permission) => ({ permission, scope_type: 'global' as const, scope_id: null })),
    ],
  }
  const departmentAdmin = {
    ...USER,
    department: { id: department.id, name: department.name },
    roles: ['user', 'department_admin'],
    grants: [
      ...USER.grants,
      ...[
        'department:read',
        'department_member:read',
        'department_member:add',
        'department_member:remove',
      ].map((permission) => ({
        permission,
        scope_type: 'department' as const,
        scope_id: department.id,
      })),
    ],
  }
  return { USER, LOGIN, CREDENTIALS, admin, departmentAdmin, department, member, managedUser }
}
