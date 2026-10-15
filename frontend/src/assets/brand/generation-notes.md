# 青蓝水墨素材生成记录

当前品牌素材为青蓝水墨图像与舟形 SVG 标志，均已应用到正式聊天界面。

- [水墨背景](indigo-ink.png)：由内置 imagegen 生成，1536×1024，保留原始透明通道；由 `RiverBackdrop.vue` 裁切铺满首页主区域，动画由 CSS 实现。
- [舟与航迹标志](mark-river.svg)：项目原创矢量图形，通过 currentColor 与强调色适配主题；`BrandLogo.vue` 与 favicon 采用同一舟形。

## 最终提示词

### indigo

```text
Use case: stylized-concept. Asset type: transparent contemporary Chinese ink-wash artwork for an editorial web app hero. Paint a wide flowing horizontal river of deep indigo #142C3E and teal #167C91 ink, layers of translucent distant mountain silhouettes dissolving into mist, pale turquoise watercolor diffusion, one tiny abstract white-sailed boat on the right. Expansive panoramic feeling, very refined, atmospheric but with decisive saturated dark ink contrasts, handmade brush texture, strong horizontal movement and open breathing space above the water. Landscape 3:2 composition, artwork across bottom half and right edge, mostly transparent upper left. Genuine transparent alpha background, including mist feathered edges, no rectangular colored background. No letters, no characters, no logos, no seal, no UI, no watermark, no frame.
```
