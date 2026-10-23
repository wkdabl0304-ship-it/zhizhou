/** 过程组件回归：验证多次执行与有效空值的展示，防止工具内容被解释为 HTML。 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import AgentActivity from '../../components/AgentActivity.vue'

describe('过程卡片展示', () => {
  // 工具返回内容与命令参数不能执行为 HTML；null/false/0 和多次执行都必须真实显示。
  it('折叠展示进度正文与命令详情，保留有效空值并转义不可信内容', () => {
    const wrapper = mount(AgentActivity, {
      props: {
        activities: [
          {
            id: 'thinking',
            type: 'text',
            messageId: 'm',
            text: '<script>进度正文文本</script>',
            status: 'complete',
          },
          {
            id: 'cmd',
            type: 'tool',
            toolCallId: 'cmd',
            name: 'runner',
            kind: 'command',
            status: 'complete',
            runs: [
              {
                runId: '1',
                kind: 'command',
                status: 'error',
                arguments: '<img src=x onerror=alert(1)>',
                error: '执行失败',
              },
              { runId: '2', kind: 'command', status: 'complete', arguments: 'pwd', output: null },
              { runId: '3', kind: 'command', status: 'complete', output: 0 },
              { runId: '4', kind: 'command', status: 'complete', output: false },
            ],
          },
          {
            id: 'queued',
            type: 'tool',
            toolCallId: 'queued',
            name: 'lookup',
            status: 'queued',
            arguments: {},
            runs: [],
          },
        ],
      },
    })
    expect(wrapper.findAll('details')).toHaveLength(2)
    expect(wrapper.get('details').attributes('open')).toBeUndefined()
    expect(wrapper.text()).toContain('<script>进度正文文本</script>')
    expect(wrapper.text()).toContain('命令执行')
    expect(wrapper.text()).toContain('第 2 次执行')
    expect(wrapper.text()).toContain('已请求，等待执行')
    expect(wrapper.findAll('pre').map((node) => node.text())).toEqual(
      expect.arrayContaining(['null', '0', 'false', 'pwd']),
    )
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.find('img').exists()).toBe(false)
  })
})
