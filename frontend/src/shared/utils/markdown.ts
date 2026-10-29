/** 聊天 Markdown 渲染：集中管理安全选项、代码高亮和受控的 HTML 包装，不接收原始 HTML。 */
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js/lib/core'
import javascript from 'highlight.js/lib/languages/javascript'
import typescript from 'highlight.js/lib/languages/typescript'
import python from 'highlight.js/lib/languages/python'
import json from 'highlight.js/lib/languages/json'
import bash from 'highlight.js/lib/languages/bash'
import css from 'highlight.js/lib/languages/css'
import xml from 'highlight.js/lib/languages/xml'
import sql from 'highlight.js/lib/languages/sql'
import markdown from 'highlight.js/lib/languages/markdown'
import yaml from 'highlight.js/lib/languages/yaml'

// 只注册常用语法，避免将全部语言打入聊天页面；未知语言保持转义后的纯文本。
hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('typescript', typescript)
hljs.registerLanguage('python', python)
hljs.registerLanguage('json', json)
hljs.registerLanguage('bash', bash)
hljs.registerLanguage('css', css)
hljs.registerLanguage('xml', xml)
hljs.registerLanguage('sql', sql)
hljs.registerLanguage('markdown', markdown)
hljs.registerLanguage('yaml', yaml)

const parser = new MarkdownIt({ html: false, breaks: true, linkify: true })

/**
 * 将代码块渲染为带语法高亮和复制按钮的 HTML。
 * source 是代码原文，info 提供语言标签；已注册语言由本地高亮器处理，
 * 未知语言及标签先转义，返回同一套包装结构供 Markdown 组件展示。
 */
function renderCode(source: string, info: string): string {
  const language = parser.utils.unescapeAll(info).trim().split(/\s+/)[0] || 'text'
  const code = hljs.getLanguage(language)
    ? hljs.highlight(source, { language, ignoreIllegals: true }).value
    : parser.utils.escapeHtml(source)
  return `<div class="markdown-code"><div class="markdown-code-heading"><span>${parser.utils.escapeHtml(language)}</span><button type="button" class="markdown-code-copy ui-button ui-button--ghost ui-button--sm">复制代码</button></div><pre><code class="hljs">${code}</code></pre></div>\n`
}

// 围栏与缩进代码使用一致的外观和复制入口；未闭合的流式围栏也可由解析器正常渲染。
parser.renderer.rules.fence = (tokens, index) =>
  renderCode(tokens[index]!.content, tokens[index]!.info)
// 将缩进代码交给同一渲染入口，无语言标签时按纯文本展示。
parser.renderer.rules.code_block = (tokens, index) => renderCode(tokens[index]!.content, '')

// Markdown 链接仍由解析器校验协议；打开新页时隔离 opener，防止丢失当前聊天页面。
parser.renderer.rules.link_open = (tokens, index, options, _env, renderer) => {
  tokens[index]!.attrSet('target', '_blank')
  tokens[index]!.attrSet('rel', 'noopener noreferrer')
  return renderer.renderToken(tokens, index, options)
}

// 表格单独横向滚动，保证窄屏页面和底部输入区不被宽内容撑开。
parser.renderer.rules.table_open = () =>
  '<div class="markdown-table" tabindex="0" role="region" aria-label="表格，可横向滚动"><table>\n'
// 结束表格时同步关闭滚动容器，使后续 Markdown 不进入表格区域。
parser.renderer.rules.table_close = () => '</table></div>\n'

/** 将助手提供的 Markdown 源文转换为受控 HTML；原始 HTML 作为文本显示。 */
export function renderMarkdown(source: string): string {
  return parser.render(source)
}
