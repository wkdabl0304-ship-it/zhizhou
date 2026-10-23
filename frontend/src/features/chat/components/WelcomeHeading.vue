<!-- 首页品牌标题：现代宋体结合错拍浮动、青蓝流光与水线；纯 CSS 动效不改变排版，并遵循系统减少动态效果偏好。 -->
<template>
  <h2 class="river-heading">
    <span class="heading-line heading-line--first"><span class="heading-ink">心有山海，</span></span
    ><br />
    <span class="heading-line heading-line--second"
      ><span class="heading-ink">自有</span><span class="heading-brand">知舟。</span></span
    >
  </h2>
</template>
<style scoped>
.river-heading {
  min-height: 157px;
  margin: 18px 0 16px;
  color: var(--text);
  font-family: 'Noto Serif CJK SC', 'Source Han Serif SC', 'Songti SC', STSong, SimSun, serif;
  font-size: clamp(54px, 5.2vw, 74px);
  font-weight: 700;
  letter-spacing: 4px;
  line-height: 1.12;
}
.heading-line {
  display: inline-block;
  animation: heading-float 5s ease-in-out -1s infinite alternate;
}
.heading-line--second {
  animation-delay: -3.5s;
}
.heading-brand {
  position: relative;
  display: inline-block;
  color: var(--brand);
}
/* 光带只在字形内移动，不使用透明度闪烁；不支持文字裁切时保留原本的实色标题。 */
@supports (background-clip: text) or (-webkit-background-clip: text) {
  .heading-ink,
  .heading-brand {
    background-image: linear-gradient(110deg, var(--text) 15%, var(--brand) 38%, var(--text) 60%);
    background-size: 240% 100%;
    background-clip: text;
    -webkit-background-clip: text;
    color: transparent;
    animation: heading-ink-flow 6s ease-in-out -2s infinite alternate;
  }
  .heading-brand {
    background-image: linear-gradient(
      110deg,
      var(--brand) 15%,
      var(--brand-hover) 32%,
      var(--text) 46%,
      var(--brand) 62%
    );
    animation-delay: -4s;
  }
}
/* 水线与文字错速伸展，独立于文字流光，保持标题的品牌强调。 */
.heading-brand::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0.03em;
  height: 3px;
  border-radius: 50%;
  background: linear-gradient(
    90deg,
    transparent,
    var(--brand),
    color-mix(in srgb, var(--brand) 28%, transparent),
    transparent
  );
  transform-origin: left center;
  animation: heading-waterline 3.5s ease-in-out -1s infinite alternate;
}
@keyframes heading-float {
  from {
    transform: translate3d(0, 2px, 0);
  }
  to {
    transform: translate3d(0, -4px, 0);
  }
}
@keyframes heading-ink-flow {
  from {
    background-position: 100% 50%;
  }
  to {
    background-position: 0% 50%;
  }
}
@keyframes heading-waterline {
  from {
    transform: scaleX(0.72);
    opacity: 0.5;
  }
  to {
    transform: scaleX(1.04);
    opacity: 0.95;
  }
}
@media (max-width: 760px) {
  .river-heading {
    min-height: 113px;
    margin-top: 22px;
    font-size: 49px;
    letter-spacing: 0;
  }
}
/* 组件在独立使用时也遵循系统偏好，停在清晰可读的静态构图。 */
@media (prefers-reduced-motion: reduce) {
  .heading-line,
  .heading-ink,
  .heading-brand,
  .heading-brand::after {
    animation: none;
  }
}
</style>
