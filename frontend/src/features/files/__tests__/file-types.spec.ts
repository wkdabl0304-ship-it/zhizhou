/** 文件类型外观测试：覆盖常见格式、大小写、伪装后缀、目录和未知格式回退。 */
import { expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { describeFile } from '../file-types'
import FileTypeIcon from '../components/FileTypeIcon.vue'

it.each([
  ['年度报告.PDF', 'pdf'],
  ['方案.docx', 'word'],
  ['数据.XLSX', 'sheet'],
  ['列表.csv', 'sheet'],
  ['演示.pptx', 'slides'],
  ['山水.svg', 'image'],
  ['合影.JPEG', 'image'],
  ['录音.flac', 'audio'],
  ['课程.mp4', 'video'],
  ['备份.tar.gz', 'archive'],
  ['入口.vue', 'code'],
  ['设置.env', 'code'],
  ['Dockerfile', 'code'],
  ['笔记.md', 'text'],
  ['说明.txt', 'text'],
  ['README', 'text'],
  ['阅读.epub', 'ebook'],
  ['数据.sqlite3', 'database'],
  ['report.pdf.exe', 'application'],
  ['无后缀', 'other'],
  ['未知.自定义', 'other'],
])('%s 使用可辨认的 %s 图标和类型说明', (name, category) => {
  const appearance = describeFile(name)
  expect(appearance.category).toBe(category)
  const wrapper = mount(FileTypeIcon, { props: { name, kind: 'file' } })
  expect(wrapper.get('[role=img]').attributes('aria-label')).toBe(appearance.label)
  expect(wrapper.get('[role=img]').attributes('data-kind')).toBe(category)
  expect(wrapper.find('svg').exists()).toBe(true)
  expect(wrapper.find('img').exists()).toBe(false)
})

it('目录优先使用分层文件夹图标，改名后类型与可读标签随公开文件名更新', async () => {
  const wrapper = mount(FileTypeIcon, { props: { name: '资料.pdf', kind: 'folder' } })
  expect(wrapper.get('[role=img]').attributes('data-kind')).toBe('folder')
  await wrapper.setProps({ name: '资料.pdf', kind: 'file' })
  expect(wrapper.text()).toBe('PDF')
  await wrapper.setProps({ name: '数据.xlsx' })
  expect(wrapper.get('[role=img]').attributes('data-kind')).toBe('sheet')
  expect(wrapper.text()).toBe('XLSX')
  expect(describeFile('文件.超长扩展名').badge).toBe('FILE')
})

it.each(['light', 'dark'])('%s 主题使用统一造型并保留唯一格式标签与可访问名称', (theme) => {
  document.documentElement.dataset.theme = theme
  const wrapper = mount(FileTypeIcon, { props: { name: '项目方案.docx', kind: 'file' } })
  expect(wrapper.get('[role=img]').attributes('aria-label')).toBe('文字文档')
  expect(wrapper.text()).toBe('DOCX')
  expect(wrapper.findAll('text')).toHaveLength(1)
})
