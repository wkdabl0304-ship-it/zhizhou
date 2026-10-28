/** 管理操作授权：与导航共用有效授权事实，处理表单打开后的动态降权。 */
import type { AuthUser } from '@/features/auth/types'
import { hasGrant } from '@/features/auth/permissions'
import type { ManagementAction } from './types'

/** 判断冻结操作目标是否仍在当前权限范围内，部门绑定失效后不得提交旧表单。 */
export function canPerformAction(user: AuthUser | null, action: ManagementAction): boolean {
  if (action.kind === 'add-member' || action.kind === 'remove-member')
    return hasGrant(
      user,
      action.kind === 'add-member' ? 'department_member:add' : 'department_member:remove',
      action.department.id,
    )
  const operations = {
    'create-department': 'department:create',
    'rename-department': 'department:update',
    'delete-department': 'department:delete',
    'assign-department-admin': 'role:assign',
    'revoke-department-admin': 'role:revoke',
    'enable-user': 'user:set_active',
    'disable-user': 'user:set_active',
    'reset-password': 'user:reset_password',
    'assign-super-admin': 'role:assign',
    'revoke-super-admin': 'role:revoke',
  } as const
  return hasGrant(user, operations[action.kind])
}
