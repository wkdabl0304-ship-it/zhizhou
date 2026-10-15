# 水墨素材生成记录

本目录记录品牌探索素材。青蓝水墨 `indigo-ink.png` 和 `mark-river.svg` 已应用到正式聊天界面；其他素材仅由开发预览引用。三幅 PNG 均由内置 imagegen 工具生成，保留原始透明通道和分辨率；三款 SVG 为项目原创矢量标志，不属于模型图像输出。

素材对应：[宣纸朱砂](cinnabar-ink.png)、[青蓝水墨](indigo-ink.png)、[黑白飞白](monochrome-ink.png)。三幅均为 1536×1024 的原始透明 PNG。使用位置见品牌预览设计配置，最终配色与交互以真实 DOM 为准。

原创矢量标志：[朱砂舟形](mark-paper.svg)、[青蓝舟形](mark-river.svg)、[黑白舟形](mark-mono.svg)。SVG 使用 currentColor；正式界面的 `BrandLogo` 和 favicon 统一采用青蓝舟形，其他两种形状保留为探索草案。

## 最终提示词

### cinnabar

```text
Use case: stylized-concept. Asset type: transparent editorial website hero artwork, not a screenshot and not a logo. Create a striking Chinese ink-wash artwork for Zhizhou, a knowledge workspace, with a bold diagonal jet-black brushstroke sweeping upward like the wake of a boat, subtle pooled ink and feathered dry-brush edges, a small vivid cinnabar vermilion sun offset near upper right, one very tiny minimal boat silhouette within the lower flowing stroke. Sophisticated contemporary art direction, bold silhouette, fine rice-paper ink texture only within paint, no full paper rectangle. Landscape 3:2 composition, artwork primarily on right two-thirds, generous fully transparent negative space at left and around edges. Palette charcoal ink and cinnabar #BB3A2F only. Genuine transparent alpha background. No letters, no Chinese characters, no calligraphy text, no seals, no UI, no watermark, no frame, no photorealistic objects.
```

### indigo

```text
Use case: stylized-concept. Asset type: transparent contemporary Chinese ink-wash artwork for an editorial web app hero. Paint a wide flowing horizontal river of deep indigo #142C3E and teal #167C91 ink, layers of translucent distant mountain silhouettes dissolving into mist, pale turquoise watercolor diffusion, one tiny abstract white-sailed boat on the right. Expansive panoramic feeling, very refined, atmospheric but with decisive saturated dark ink contrasts, handmade brush texture, strong horizontal movement and open breathing space above the water. Landscape 3:2 composition, artwork across bottom half and right edge, mostly transparent upper left. Genuine transparent alpha background, including mist feathered edges, no rectangular colored background. No letters, no characters, no logos, no seal, no UI, no watermark, no frame.
```

### monochrome

```text
Use case: stylized-concept. Asset type: transparent monochrome abstract Chinese dry-brush artwork for bold modern editorial web interface. Create one monumental black flying-white feibai brush gesture, tall asymmetrical open arc rising diagonally, dramatically rough bristle striations and broken dry-ink texture, a sweep reminiscent of an abstract boat sail and its wake without becoming a literal icon. Deep dense blacks next to exposed negative space and delicate charcoal ink spray. Strong contemporary gallery poster feeling, minimal and confident. Landscape 3:2 canvas, large artwork concentrated on right two-thirds, transparent left margin and transparent negative space inside and around brushwork. Black and gray ink only. Genuine transparent alpha background. No letters, no Chinese characters, no calligraphy text, no seals, no logos, no UI, no watermark, no frame, no white rectangle.
```
