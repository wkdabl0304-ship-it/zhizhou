/** Markdown 正文回归：验证富文本结构、流式重渲染、代码复制以及不可信内容的安全边界。 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import MarkdownContent from '@/shared/components/MarkdownContent.vue'

const wrappers: VueWrapper[] = []

/** 渲染实际正文组件，保留 Markdown 解析、高亮和事件委托，不触发外部网络请求。 */
function render(source: string) {
  const wrapper = mount(MarkdownContent, { props: { source } })
  wrappers.push(wrapper)
  return wrapper
}

// 卸载组件并恢复剪贴板替身，避免访问系统剪贴板或影响其他用例。
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  vi.unstubAllGlobals()
})

describe('助手 Markdown 富文本', () => {
  // 覆盖常见大模型回复中的块级和行内格式，表格放在独立的可滚动区域。
  it('渲染标题、强调、列表、引用、表格和行内代码', () => {
    const wrapper = render(
      [
        '# 工作计划',
        '',
        '**重点**、*说明*、~~过时内容~~和 `thread_id`。',
        '',
        '1. 第一步',
        '2. 第二步',
        '   - 子任务',
        '',
        '> 引用说明',
        '',
        '| 项目 | 状态 |',
        '| --- | --- |',
        '| 聊天 | **完成** |',
        '',
        '---',
        '',
        '第一行',
        '第二行',
      ].join('\n'),
    )
    expect(wrapper.get('h1').text()).toBe('工作计划')
    expect(wrapper.findAll('strong').map((node) => node.text())).toEqual(['重点', '完成'])
    expect(wrapper.get('em').text()).toBe('说明')
    expect(wrapper.get('s').text()).toBe('过时内容')
    expect(wrapper.get('code').text()).toBe('thread_id')
    expect(wrapper.findAll('ol > li')).toHaveLength(2)
    expect(wrapper.get('ol ul li').text()).toBe('子任务')
    expect(wrapper.get('blockquote').text()).toBe('引用说明')
    expect(wrapper.get('.markdown-table table th').text()).toBe('项目')
    expect(wrapper.find('hr').exists()).toBe(true)
    expect(wrapper.find('br').exists()).toBe(true)
  })

  // 流式文本允许暂未闭合；新的分隔符到达后重新解析源文，不留下旧 HTML 或重复正文。
  it('随流式增量更新强调和未闭合代码围栏', async () => {
    const wrapper = render('**正在生成')
    expect(wrapper.text()).toContain('正在生成')
    await wrapper.setProps({ source: '**正在生成完成**\n\n```python\nprint("你好")' })
    expect(wrapper.get('strong').text()).toBe('正在生成完成')
    expect(wrapper.get('pre code').text()).toContain('print("你好")')
    await wrapper.setProps({ source: '**最终回答**\n\n```python\nprint("完成")\n```' })
    expect(wrapper.get('strong').text()).toBe('最终回答')
    expect(wrapper.get('pre code').element.textContent).toBe('print("完成")\n')
    expect(wrapper.findAll('pre')).toHaveLength(1)
    expect(wrapper.text()).not.toContain('你好')
  })

  // 模型原始 HTML 一律作为文字；危险协议也不能由 Markdown 链接或图片进入 DOM。
  it('转义 HTML 和代码标签，拒绝脚本链接及 SVG data 图片', () => {
    const wrapper = render(
      [
        '<img src=x onerror=alert(1)><script>alert(1)</script>',
        '',
        '[危险](javascript:alert%281%29)',
        '[实体危险](javascript&#x3A;alert%281%29)',
        '![危险图片](data:image/svg+xml;base64,PHN2Zz4=)',
        '',
        '[正常链接](https://example.com/docs)',
        '',
        '```html',
        '<iframe src="https://example.com"></iframe>',
        '```',
        '',
        '~~~<img',
        '<svg onload=alert(1)>',
        '~~~',
      ].join('\n'),
    )
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.find('iframe').exists()).toBe(false)
    expect(wrapper.find('svg').exists()).toBe(false)
    expect(wrapper.find('[onerror]').exists()).toBe(false)
    expect(wrapper.findAll('a')).toHaveLength(1)
    expect(wrapper.get('a').attributes()).toMatchObject({
      href: 'https://example.com/docs',
      target: '_blank',
      rel: 'noopener noreferrer',
    })
    expect(wrapper.findAll('pre code')[0]!.text()).toContain('<iframe')
  })

  // 已知语言显示高亮，未知语言仍可阅读和复制；复制只包含当前代码块，不含高亮 span。
  it('高亮常用语言并分别复制多个代码块', async () => {
    const writeText = vi.fn<(text: string) => Promise<void>>().mockResolvedValue()
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    const wrapper = render(
      '```js\nconst value = 42\n```\n\n```unknown-language\n<b>literal</b>\n```',
    )
    expect(wrapper.find('code .hljs-keyword').exists()).toBe(true)
    expect(wrapper.find('b').exists()).toBe(false)
    const buttons = wrapper.findAll('button.markdown-code-copy')
    await buttons[0]!.trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenLastCalledWith('const value = 42\n')
    await buttons[1]!.trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenLastCalledWith('<b>literal</b>\n')
    expect(wrapper.get('[role="status"]').text()).toBe('代码已复制')
  })

  // 剪贴板权限失败通过组件内状态反馈，不丢失代码，也不抛出未处理异常。
  it('代码复制失败后提供手动复制提示', async () => {
    vi.stubGlobal('navigator', {
      clipboard: {
        writeText: vi.fn<(text: string) => Promise<void>>().mockRejectedValue(new Error('denied')),
      },
    })
    const wrapper = render('```text\n需要保留的代码\n```')
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toContain('复制失败')
    expect(wrapper.get('pre code').element.textContent).toBe('需要保留的代码\n')
  })
})
