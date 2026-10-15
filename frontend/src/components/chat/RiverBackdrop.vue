<!-- 首页环境背景：铺满主区域的水墨、流雾与水面光带；独立于标题宽度和滚动内容，仅使用 CSS 变换播放。 -->
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
  inset: -5%;
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
/* 流雾和水面光带与山体使用不同的速度，避免把整个页面当作一张图片晃动。 */
.river-mist {
  position: absolute;
  inset: 20% -20% -10%;
  background:
    radial-gradient(
      ellipse at 30% 60%,
      color-mix(in srgb, var(--bg) 72%, transparent),
      transparent 40%
    ),
    radial-gradient(
      ellipse at 75% 70%,
      color-mix(in srgb, var(--bg) 58%, transparent),
      transparent 34%
    );
  opacity: 0.65;
}
.river-current {
  position: absolute;
  inset: 48% -35% 8%;
  background: linear-gradient(
    105deg,
    transparent 35%,
    color-mix(in srgb, var(--bg) 60%, transparent) 48%,
    transparent 62%
  );
  filter: blur(16px);
  opacity: 0.5;
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
  animation: river-landscape-flow 28s ease-in-out infinite alternate;
}
.river-backdrop[data-motion='on'] .river-mist {
  animation: river-mist-flow 19s ease-in-out infinite alternate;
}
.river-backdrop[data-motion='on'] .river-current {
  animation: river-current-flow 23s ease-in-out infinite alternate;
}
@keyframes river-landscape-flow {
  from {
    transform: translate3d(-1.2%, 0, 0) scale(1.025);
  }
  to {
    transform: translate3d(1.2%, -1%, 0) scale(1.055);
  }
}
@keyframes river-mist-flow {
  from {
    transform: translate3d(-7%, 2%, 0);
    opacity: 0.45;
  }
  to {
    transform: translate3d(7%, -2%, 0);
    opacity: 0.8;
  }
}
@keyframes river-current-flow {
  from {
    transform: translate3d(-18%, 0, 0);
    opacity: 0.25;
  }
  to {
    transform: translate3d(18%, 3%, 0);
    opacity: 0.6;
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
  .river-backdrop[data-motion] > * {
    animation: none;
  }
}
</style>
