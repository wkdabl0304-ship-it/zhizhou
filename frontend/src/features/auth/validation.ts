/** 认证表单规则：对齐后端的用户名与密码要求，保持密码原文，仅在前端校验确认密码。 */
import type { AuthMode } from './types'

/** 校验表单并返回可直接显示的字段错误；密码按 Unicode 字符计数，与 Python 长度规则一致。 */
export function validateAuth(
  mode: AuthMode,
  username: string,
  password: string,
  confirmation: string,
) {
  const normalized = username.trim().toLowerCase()
  const length = Array.from(password).length
  return {
    username: !normalized
      ? '请输入用户名'
      : /^[a-z0-9_]{3,32}$/.test(normalized)
        ? ''
        : '用户名须为 3–32 位字母、数字或下划线',
    password: !password
      ? '请输入密码'
      : length < 8 || length > 128
        ? '密码长度须为 8–128 个字符'
        : '',
    confirmation: mode === 'register' && password !== confirmation ? '两次输入的密码不一致' : '',
  }
}

/** 限定登录后的跳转目的地为本应用现有入口，拒绝外部网址、反斜杠和认证页循环。 */
export function postLoginPath(value: unknown): string {
  if (
    typeof value !== 'string' ||
    !value.startsWith('/') ||
    value.startsWith('//') ||
    /[\\\r\n]/.test(value)
  )
    return '/'
  const path = value.split(/[?#]/)[0]
  return path === '/' || path === '/dev/ui' ? value : '/'
}
