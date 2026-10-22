/** 认证表单测试：验证对外提交数据、字段约束、密码显隐及等待中的重复提交边界。 */
import { afterEach, describe, expect, it } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import AuthForm from '../AuthForm.vue'
import { postLoginPath, validateAuth } from '../validation'

const wrappers: VueWrapper[] = []
/** 创建独立表单实例，统一在用例结束后卸载。 */
function form(mode: 'login' | 'register' = 'login') {
  const wrapper = mount(AuthForm, { props: { mode } })
  wrappers.push(wrapper)
  return wrapper
}
// 卸载 DOM 与事件监听，不跨用例保留密码输入。
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
})

describe('认证表单', () => {
  // 用户名可标准化，密码必须保留首尾空格；确认值不会传给接口层。
  it('标准化用户名并原样提交密码', async () => {
    const wrapper = form('register')
    await wrapper.get('[name="username"]').setValue('  Lin_Zhou  ')
    await wrapper.get('[name="password"]').setValue(' password ')
    await wrapper.get('[name="confirmation"]').setValue(' password ')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')).toEqual([[{ username: 'lin_zhou', password: ' password ' }]])
    expect(wrapper.find('[name="role"]').exists()).toBe(false)
  })

  // 错误的账号、短密码和确认不符都应阻止请求并关联到对应输入框。
  it('字段不合法时展示错误并阻止提交', async () => {
    const wrapper = form('register')
    await wrapper.get('[name="username"]').setValue('中文')
    await wrapper.get('[name="password"]').setValue('short')
    await wrapper.get('[name="confirmation"]').setValue('different')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.text()).toContain('用户名须为')
    expect(wrapper.text()).toContain('密码长度须为')
    expect(wrapper.text()).toContain('两次输入的密码不一致')
    expect(wrapper.get('[name="username"]').attributes('aria-invalid')).toBe('true')
  })

  // 采用 Python 字符长度规则，避免把单个 emoji 按两个 UTF-16 码元计数。
  it('按 Unicode 字符处理密码长度上下界', () => {
    expect(validateAuth('login', 'abc', '😀'.repeat(7), '').password).not.toBe('')
    expect(validateAuth('login', 'abc', '😀'.repeat(8), '').password).toBe('')
    expect(validateAuth('login', 'abc', '😀'.repeat(128), '').password).toBe('')
    expect(validateAuth('login', 'abc', '😀'.repeat(129), '').password).not.toBe('')
    expect(validateAuth('register', 'a'.repeat(32), '12345678', '12345678').username).toBe('')
    expect(validateAuth('register', 'a'.repeat(33), '12345678', '12345678').username).not.toBe('')
  })

  // 显隐只影响本表单，进入等待状态后禁用所有输入且阻止重复提交。
  it('支持密码显隐，等待时禁止重复提交', async () => {
    const wrapper = form()
    await wrapper.get('[name="username"]').setValue('lin_zhou')
    await wrapper.get('[name="password"]').setValue('12345678')
    expect(wrapper.get('[name="password"]').attributes('type')).toBe('password')
    await wrapper.get('[aria-label="显示密码"]').trigger('click')
    expect(wrapper.get('[name="password"]').attributes('type')).toBe('text')
    await wrapper.get('form').trigger('submit')
    await wrapper.setProps({ busy: true })
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')).toHaveLength(1)
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[name="password"]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('正在登录')
  })

  // 服务端错误只能作为文本展示，重名错误关联用户名且不解释为 HTML。
  it('展示接口错误并保持 HTML 内容为文本', async () => {
    const wrapper = form()
    await wrapper.setProps({ error: '<b>凭据错误</b>', usernameError: '用户名已存在' })
    expect(wrapper.text()).toContain('<b>凭据错误</b>')
    expect(wrapper.find('b').exists()).toBe(false)
    expect(wrapper.get('[name="username"]').attributes('aria-invalid')).toBe('true')
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
    '/\n',
  ])('拒绝不安全或不存在的返回地址 %#', (value) => {
    expect(postLoginPath(value)).toBe('/')
  })
  // 查询参数和片段可跟随合法内部入口保留，不执行其中的外部地址。
  it.each(['/', '/?from=login#composer', '/dev/ui'])('保留合法内部地址 %s', (value) => {
    expect(postLoginPath(value)).toBe(value)
  })
})
