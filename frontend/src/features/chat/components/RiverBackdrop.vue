<!-- 首页环境背景：山景、双层流雾与水面光带错速流动，独立于标题和输入区；使用 CSS 动画并遵循减少动态效果偏好。 -->
<script setup lang="ts">
import riverArtwork from '@/assets/brand/indigo-ink.png'
withDefaults(defineProps<{ motion?: boolean }>(), { motion: true })
</script>
<template>
  <div class="river-backdrop" :data-motion="motion ? 'on' : 'off'" aria-hidden="true">
    <div class="river-landscape">
      <img class="river-landscape-art" :src="riverArtwork" alt="" fetchpriority="high" />
    </div>
    <div class="river-mist" />
    <div class="river-current" />
    <div class="river-wash" />
  </div>
</template>
<style scoped>
/* 外层只裁切装饰，超出边界的画布为漂移留出余量，静态及动画端点都不会露出矩形边缘。 */
.river-backdrop {
  position: absolute;
  z-index: -1;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
  background: var(--bg);
}
.river-landscape {
  position: absolute;
  inset: -8%;
  opacity: 0.85;
}
.river-landscape-art {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center 64%;
  filter: var(--hero-art-filter);
}
/* 狭长雾带形成可辨认的前景，和山景错向移动；扩大画布为位移保留裁切余量。 */
.river-mist {
  position: absolute;
  inset: 28% -25% -12%;
  background:
    radial-gradient(
      ellipse 42% 12% at 26% 46%,
      color-mix(in srgb, var(--surface) 86%, transparent),
      transparent 76%
    ),
    radial-gradient(
      ellipse 36% 10% at 76% 70%,
      color-mix(in srgb, var(--surface) 76%, transparent),
      transparent 78%
    );
  filter: blur(8px);
  opacity: 0.8;
}
/* 第二层薄雾独立运动，形成掠过山腰的层次，避免只放大原图的整体位移。 */
.river-mist::after {
  content: '';
  position: absolute;
  inset: 4% -8% 16%;
  background: radial-gradient(
    ellipse 48% 9% at 50% 52%,
    color-mix(in srgb, var(--surface) 88%, transparent),
    transparent 78%
  );
}
.river-current {
  position: absolute;
  inset: 56% -35% -8%;
  background:
    radial-gradient(
      ellipse 28% 5% at 36% 56%,
      color-mix(in srgb, var(--brand) 30%, transparent),
      transparent 80%
    ),
    radial-gradient(
      ellipse 32% 4% at 65% 76%,
      color-mix(in srgb, var(--surface) 94%, transparent),
      transparent 80%
    ),
    linear-gradient(
      108deg,
      transparent 30%,
      color-mix(in srgb, var(--surface) 72%, transparent) 46%,
      transparent 62%
    );
  filter: blur(5px);
  opacity: 0.75;
}
/* 文字附近留出柔和的纸面，底部渐淡保障说明文字对比度，蒙层本身不参与动画。 */
.river-wash {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(
      ellipse at 50% 32%,
      color-mix(in srgb, var(--bg) 88%, transparent),
      transparent 48%
    ),
    linear-gradient(
      180deg,
      color-mix(in srgb, var(--bg) 36%, transparent),
      transparent 50%,
      color-mix(in srgb, var(--bg) 80%, transparent)
    );
}
.river-backdrop[data-motion='on'] .river-landscape {
  animation: river-landscape-flow 14s ease-in-out -5s infinite alternate;
}
.river-backdrop[data-motion='on'] .river-mist {
  animation: river-mist-flow 9s ease-in-out -3s infinite alternate;
}
.river-backdrop[data-motion='on'] .river-mist::after {
  animation: river-mist-counterflow 7s ease-in-out -2s infinite alternate;
}
.river-backdrop[data-motion='on'] .river-current {
  animation: river-current-flow 8s ease-in-out -4s infinite alternate;
}
@keyframes river-landscape-flow {
  from {
    transform: translate3d(-3%, 1.2%, 0) scale(1.04);
  }
  to {
    transform: translate3d(3%, -1.8%, 0) scale(1.09);
  }
}
@keyframes river-mist-flow {
  from {
    transform: translate3d(12%, 3%, 0);
    opacity: 0.55;
  }
  to {
    transform: translate3d(-12%, -3%, 0);
    opacity: 0.95;
  }
}
@keyframes river-mist-counterflow {
  from {
    transform: translate3d(-8%, 4%, 0);
  }
  to {
    transform: translate3d(10%, -4%, 0);
  }
}
@keyframes river-current-flow {
  from {
    transform: translate3d(-20%, 2%, 0) skewX(-6deg);
    opacity: 0.45;
  }
  to {
    transform: translate3d(20%, -2%, 0) skewX(6deg);
    opacity: 0.9;
  }
}
@media (max-width: 760px) {
  .river-landscape-art {
    object-position: 62% center;
  }
  .river-landscape {
    opacity: 0.65;
  }
  .river-mist {
    opacity: 0.4;
  }
}
/* 组件本身也保护系统偏好，独立预览不依赖聊天页的外层动画规则。 */
@media (prefers-reduced-motion: reduce) {
  .river-backdrop[data-motion] > *,
  .river-backdrop[data-motion] .river-mist::after {
    animation: none;
  }
}
</style>
