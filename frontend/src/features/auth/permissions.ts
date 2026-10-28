/** 身份授权规则：精确匹配操作与范围，供路由、导航和业务按钮共用。 */
import type { AuthUser } from './types'

/** 判断具体操作能否作用于目标；不传目标时只接受全局授权。 */
export function hasGrant(user: AuthUser | null, permission: string, scopeId?: string): boolean {
  return !!user?.grants.some(
    (grant) =>
      grant.permission === permission &&
      (grant.scope_type === 'global' ||
        (scopeId !== undefined &&
          grant.scope_id === scopeId &&
          ((grant.scope_type === 'department' && user.department?.id === scopeId) ||
            (grant.scope_type === 'self' && user.id === scopeId)))),
  )
}

/** 判断是否有可见组织目录或全站账号目录。 */
export function canManageOrganization(user: AuthUser | null): boolean {
  return hasGrant(user, 'user:read') || hasGrant(user, 'department:read', user?.department?.id)
}
