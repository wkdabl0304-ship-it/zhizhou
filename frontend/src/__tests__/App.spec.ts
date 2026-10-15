/**
 * 根组件的最小渲染回归测试，确认前端基础工程仍能显示初始页面。
 * 测试使用 jsdom 与 Vue Test Utils，不需要浏览器服务或后端连接。
 */
import { describe, it, expect } from 'vitest'

import { mount } from '@vue/test-utils'
import App from '../App.vue'

describe('App', () => {
  // 测试套件回调负责登记本组件的检查项，不在此启动真实应用服务。
  it('mounts renders properly', () => {
    // 将根组件挂载到测试 DOM，并检查可见文字，避免依赖组件内部实现细节。
    const wrapper = mount(App)
    expect(wrapper.text()).toContain('You did it!')
  })
})
