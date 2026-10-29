/** 文件外观分类：按公开文件名选择原创图标和类型说明，不读取或执行文件内容。 */
export type FileCategory =
  | 'folder'
  | 'pdf'
  | 'word'
  | 'sheet'
  | 'slides'
  | 'image'
  | 'audio'
  | 'video'
  | 'archive'
  | 'code'
  | 'text'
  | 'ebook'
  | 'database'
  | 'application'
  | 'other'

/** 列表中可读的类型与图标标签，未知格式仍保留明确兜底。 */
export interface FileAppearance {
  category: FileCategory
  label: string
  badge: string
}

/** 常见格式的显示分组；仅决定视觉，不代表后端已经解析或支持预览。 */
const formats: { category: FileCategory; label: string; extensions: string[] }[] = [
  { category: 'pdf', label: 'PDF 文档', extensions: ['pdf'] },
  {
    category: 'word',
    label: '文字文档',
    extensions: ['doc', 'docx', 'odt', 'rtf', 'wps', 'pages'],
  },
  {
    category: 'sheet',
    label: '电子表格',
    extensions: ['xls', 'xlsx', 'xlsm', 'csv', 'tsv', 'ods', 'et', 'numbers'],
  },
  {
    category: 'slides',
    label: '演示文稿',
    extensions: ['ppt', 'pptx', 'pps', 'ppsx', 'odp', 'dps', 'key'],
  },
  {
    category: 'image',
    label: '图片',
    extensions: [
      'png',
      'jpg',
      'jpeg',
      'gif',
      'webp',
      'svg',
      'avif',
      'bmp',
      'tif',
      'tiff',
      'ico',
      'heic',
      'psd',
      'ai',
    ],
  },
  {
    category: 'audio',
    label: '音频',
    extensions: ['mp3', 'wav', 'flac', 'aac', 'm4a', 'ogg', 'opus', 'wma'],
  },
  {
    category: 'video',
    label: '视频',
    extensions: ['mp4', 'mov', 'mkv', 'avi', 'webm', 'm4v', 'wmv', 'mpeg', 'mpg'],
  },
  {
    category: 'archive',
    label: '压缩文件',
    extensions: ['zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'xz', 'tgz', 'zst'],
  },
  {
    category: 'code',
    label: '代码与配置',
    extensions: [
      'js',
      'jsx',
      'ts',
      'tsx',
      'vue',
      'py',
      'go',
      'rs',
      'java',
      'c',
      'cpp',
      'h',
      'cs',
      'html',
      'css',
      'scss',
      'json',
      'yaml',
      'yml',
      'toml',
      'xml',
      'ini',
      'env',
      'sh',
      'ps1',
      'bat',
    ],
  },
  {
    category: 'text',
    label: '文本资料',
    extensions: ['txt', 'md', 'markdown', 'log', 'rst', 'tex'],
  },
  { category: 'ebook', label: '电子书', extensions: ['epub', 'mobi', 'azw', 'azw3'] },
  {
    category: 'database',
    label: '数据文件',
    extensions: ['sql', 'db', 'sqlite', 'sqlite3', 'parquet'],
  },
  {
    category: 'application',
    label: '应用文件',
    extensions: ['exe', 'msi', 'apk', 'dmg', 'appimage', 'deb', 'rpm'],
  },
]

/** 将文件名映射为可识别外观，扩展名忽略大小写；目录归属优先于名称后缀。 */
export function describeFile(name: string, kind: 'file' | 'folder' = 'file'): FileAppearance {
  if (kind === 'folder') return { category: 'folder', label: '文件夹', badge: '' }
  const normalized = name.trim().toLowerCase()
  const extension = normalized.includes('.') ? normalized.split('.').at(-1)! : ''
  const knownName = ['dockerfile', 'makefile'].includes(normalized)
    ? 'code'
    : ['readme', 'license', 'licence'].includes(normalized)
      ? 'text'
      : undefined
  // 只使用最后一个扩展名；例如 report.pdf.exe 必须显示为应用文件。
  const format = formats.find(
    (item) => item.category === knownName || item.extensions.includes(extension),
  )
  return {
    category: format?.category ?? 'other',
    label: format?.label ?? '其他文件',
    badge: /^[a-z0-9]{1,4}$/.test(extension)
      ? extension.toUpperCase()
      : format?.category === 'code'
        ? 'CODE'
        : 'FILE',
  }
}
