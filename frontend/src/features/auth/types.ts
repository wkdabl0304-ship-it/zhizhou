/** 认证模块类型：描述公开身份、账号输入与短期令牌，不包含密码持久化模型。 */
export type AuthMode = 'login' | 'register'

/** 有效授权的操作与资源范围；角色名称仅供展示。 */
export interface Grant {
  permission: string
  scope_type: 'global' | 'department' | 'self'
  scope_id: string | null
}

/** 公开部门摘要，不含成员及管理数据。 */
export interface DepartmentBrief {
  id: string
  name: string
}

/** 服务器返回的公开身份；角色只用于身份展示，不作为前端授权依据。 */
export interface AuthUser {
  id: string
  username: string
  role: 'user' | 'super_admin'
  department: DepartmentBrief | null
  roles: string[]
  grants: Grant[]
}

/** 仅在一次提交调用中传递的凭据，不写入浏览器存储。 */
export interface Credentials {
  username: string
  password: string
}

/** 登录成功数据；有效期以秒计，客户端用于主动结束过期界面状态。 */
export interface LoginResult {
  access_token: string
  token_type: 'bearer'
  expires_in: number
  user: AuthUser
}
