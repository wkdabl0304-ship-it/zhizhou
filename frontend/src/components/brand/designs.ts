/** 品牌探索配置：仅由开发预览引用，定义三种构图、配色、Logo 和图像素材的关系。 */
import paperArtwork from '@/assets/brand/cinnabar-ink.png'
import riverArtwork from '@/assets/brand/indigo-ink.png'
import monoArtwork from '@/assets/brand/monochrome-ink.png'
import paperMark from '@/assets/brand/mark-paper.svg?raw'
import riverMark from '@/assets/brand/mark-river.svg?raw'
import monoMark from '@/assets/brand/mark-mono.svg?raw'

export type BrandId = 'paper' | 'river' | 'mono'
export type BrandTheme = 'light' | 'dark'
export type BrandPage = 'home' | 'chat'

/** 原型设计元数据；色彩实际值在局部样式中定义，色卡用于展示设计基准。 */
export interface BrandDesign {
  id: BrandId
  number: string
  name: string
  english: string
  description: string
  logoIdea: string
  artwork: string
  mark: string
  palette: { name: string; color: string }[]
}

export const brandDesigns: BrandDesign[] = [
  {
    id: 'paper',
    number: '01',
    name: '宣纸 · 焦墨 · 朱砂',
    english: 'INK & VERMILION',
    description: '一笔浓墨，一点朱砂。东方的留白，现代的张力。',
    logoIdea: '借帆成势，以弧为舟。朱砂航迹延续笔锋，向右上方启航。',
    artwork: paperArtwork,
    mark: paperMark,
    palette: [
      { name: '宣纸', color: '#F4F0E7' },
      { name: '焦墨', color: '#171714' },
      { name: '朱砂', color: '#BB3A2F' },
    ],
  },
  {
    id: 'river',
    number: '02',
    name: '青蓝水墨',
    english: 'A CURRENT OF IDEAS',
    description: '让知识如水流动。在山海之间，找到自己的航向。',
    logoIdea: '两片流动帆面围出水滴形留白，舟身与航迹汇成同一条水路。',
    artwork: riverArtwork,
    mark: riverMark,
    palette: [
      { name: '冷白', color: '#EEF3F3' },
      { name: '深靛', color: '#142C3E' },
      { name: '青蓝', color: '#167C91' },
    ],
  },
  {
    id: 'mono',
    number: '03',
    name: '黑白 · 飞白',
    english: 'LESS NOISE. MORE THOUGHT.',
    description: '落笔有力，留白有声。把注意力，还给每一次思考。',
    logoIdea: '斜切帆面与负形桅杆构成几何舟形，宽舟身在小尺寸中保留清晰轮廓。',
    artwork: monoArtwork,
    mark: monoMark,
    palette: [
      { name: '灰白', color: '#F7F7F3' },
      { name: '墨黑', color: '#111213' },
      { name: '银灰', color: '#C7CFCA' },
    ],
  },
]

/** 只接受已定义方案标识，未知值由调用方保留当前选择。 */
export function isBrandId(value: unknown): value is BrandId {
  return value === 'paper' || value === 'river' || value === 'mono'
}
