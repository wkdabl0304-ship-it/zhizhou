/** 认证规则回归：验证密码 Unicode 边界和站内返回地址白名单，不依赖表单实现。 */
import { describe, expect, it } from 'vitest'
import { postLoginPath, validateAuth } from '../validation'

describe('认证字段校验', () => {
  // 采用 Python 字符长度规则，避免把单个 emoji 按两个 UTF-16 码元计数。
  it('按 Unicode 字符处理密码长度上下界', () => {
    expect(validateAuth('login', 'abc', '😀'.repeat(7), '').password).not.toBe('')
    expect(validateAuth('login', 'abc', '😀'.repeat(8), '').password).toBe('')
    expect(validateAuth('login', 'abc', '😀'.repeat(128), '').password).toBe('')
    expect(validateAuth('login', 'abc', '😀'.repeat(129), '').password).not.toBe('')
    expect(validateAuth('register', 'a'.repeat(32), '12345678', '12345678').username).toBe('')
    expect(validateAuth('register', 'a'.repeat(33), '12345678', '12345678').username).not.toBe('')
  })
})

describe('登录后返回地址', () => {
  // 限定为本应用真实页面，拒绝认证循环、协议相对 URL 与反斜杠重定向。
  it.each([
    undefined,
    ['/', '//evil.test'],
    'https://evil.test',
    '//evil.test',
    '/\\evil.test',
    '/login',
    '/register',
    '/unknown',
    '/organization/unknown',
    '/\n',
  ])('拒绝不安全或不存在的返回地址 %#', (value) => {
    expect(postLoginPath(value)).toBe('/')
  })
  // 查询参数和片段可跟随合法内部入口保留，不执行其中的外部地址。
  it.each([
    '/',
    '/?from=login#composer',
    '/dev/ui',
    '/models',
    '/models?from=chat',
    '/organization',
    '/organization?from=login#members',
  ])('保留合法内部地址 %s', (value) => {
    expect(postLoginPath(value)).toBe(value)
  })
})
