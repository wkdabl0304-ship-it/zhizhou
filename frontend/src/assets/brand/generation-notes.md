# 知舟山海素材生成记录

当前品牌素材包括独立的白昼水墨、月夜山海与舟形 SVG，登录页和聊天首页使用共享背景组件按主题选择图片。

- [水墨背景](indigo-ink.png)：由内置 imagegen 生成，1536×1024，保留原始透明通道；由 `RiverBackdrop.vue` 裁切铺满首页主区域，动画由 CSS 实现。
- [月夜山海](indigo-night.png)：2026-10-27 由内置 imagegen 独立生成，1536×1024、不透明夜色画布；保留月光、分层蓝墨山体和暖色舟灯，未由白昼图反相或变色生成。
- [舟与航迹标志](mark-river.svg)：项目原创矢量图形，通过 currentColor 与强调色适配主题；`BrandLogo.vue` 与 favicon 采用同一舟形。

## 最终提示词

### indigo

```text
Use case: stylized-concept. Asset type: transparent contemporary Chinese ink-wash artwork for an editorial web app hero. Paint a wide flowing horizontal river of deep indigo #142C3E and teal #167C91 ink, layers of translucent distant mountain silhouettes dissolving into mist, pale turquoise watercolor diffusion, one tiny abstract white-sailed boat on the right. Expansive panoramic feeling, very refined, atmospheric but with decisive saturated dark ink contrasts, handmade brush texture, strong horizontal movement and open breathing space above the water. Landscape 3:2 composition, artwork across bottom half and right edge, mostly transparent upper left. Genuine transparent alpha background, including mist feathered edges, no rectangular colored background. No letters, no characters, no logos, no seal, no UI, no watermark, no frame.
```

### indigo-night

使用内置 imagegen 工具生成并复制到本目录，保留原始输出；正式提示词如下：

```text
Use case: stylized-concept. Asset type: production background illustration for the dark theme of a Chinese ink-inspired chat application, wide landscape approximately 3:2, high resolution. Primary request: create an independently composed nocturnal shanshui landscape, painted for darkness from the outset, with rich indigo and midnight blue ink mountains, layered mineral-blue ridges, restrained luminous jade water, and a small warm moon-gold accent. Composition: broad quiet deep navy sky and misty negative space across the upper half and especially the upper center, suitable for light interface text added later. Mountain silhouettes frame the lower left and far right; a winding calm river leads through the lower third into a mist-filled valley. A small softly glowing pearl-gold moon at the far upper right, subtle moon reflections on water, and one tiny traditional sailing boat with a single amber light in the lower right. Style: refined contemporary Chinese ink and mineral pigment landscape on fine dark paper, expressive dry-brush mountain textures, translucent mist, exquisite restrained detail, poetic and spacious rather than photographic. Color palette anchored near #101a2b in empty sky, #1c304b and #315676 in mountain layers, subtle jade #61beb9 in water, a few warm gold #e6b975 highlights. The painting must retain layered shadow detail and gentle clear silhouettes without large white or bright cyan areas. No text, calligraphy, symbols, border, lettering, interface, logos, or watermark. Do not imitate a recolored daytime picture; use genuine nocturnal lighting and a new composition. Avoid neon, luminous fantasy effects, dramatic saturated gradients, dense stars and clutter.
```
