/** 组织管理公开契约：账号目录、部门目录和部门成员分别使用后端白名单。 */
import type { DepartmentBrief } from '@/features/auth/types'

/** 可管理部门的资料；成员数量不由此接口返回。 */
export interface Department extends DepartmentBrief {
  created_at: string
  updated_at: string
}

/** 部门成员只公开部门内角色，不据此推测全局身份。 */
export interface Member {
  id: string
  username: string
  is_active: boolean
  roles: string[]
}

/** 全站账号目录中的管理资料，不含任何私人会话或凭据。 */
export interface ManagedUser extends Member {
  department: DepartmentBrief | null
  created_at: string
  updated_at: string
}

/** 服务端游标绑定当前操作者、授权和筛选条件。 */
export interface Page<T> {
  items: T[]
  next_cursor: string | null
}

/** 列表查询只传实际选择的筛选，游标不自行解析。 */
export type Query = Record<string, string | boolean | undefined>

/** 固定操作目标的弹窗描述，避免目录刷新后将操作应用到其他行。 */
export type ManagementAction =
  | { kind: 'create-department' }
  | { kind: 'rename-department' | 'delete-department' | 'add-member'; department: Department }
  | {
      kind: 'remove-member' | 'assign-department-admin' | 'revoke-department-admin'
      department: Department
      member: Member
    }
  | {
      kind:
        | 'enable-user'
        | 'disable-user'
        | 'reset-password'
        | 'assign-super-admin'
        | 'revoke-super-admin'
      user: ManagedUser
    }
