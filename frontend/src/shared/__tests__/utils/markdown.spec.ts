/** Markdown 工具回归：覆盖无语言缩进代码的安全包装，独立于组件复制和交互。 */
import { describe, expect, it } from 'vitest'
import { renderMarkdown } from '../../utils/markdown'

describe('缩进代码包装', () => {
  it('无语言代码同样提供文本标签和复制入口，并保留原始代码', () => {
    const root = document.createElement('div')
    root.innerHTML = renderMarkdown('    <script>unsafe()</script>\n')
    expect(root.querySelector('.markdown-code-heading span')?.textContent).toBe('text')
    expect(root.querySelector('button')?.textContent).toBe('复制代码')
    expect(root.querySelector('pre code')?.textContent).toBe('<script>unsafe()</script>\n')
    expect(root.querySelector('script')).toBeNull()
  })
})
