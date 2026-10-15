<!-- 青蓝水墨首页主视觉：沿用已选方案的大字、山海画面和缓慢水墨动效，正文由其他组件承载。 -->
<script setup lang="ts">
import { ArrowDownRight } from '@lucide/vue'
import riverArtwork from '@/assets/brand/indigo-ink.png'
withDefaults(defineProps<{ motion?: boolean }>(), { motion: true })
</script>
<template>
  <section class="river-hero" :data-motion="motion ? 'on' : 'off'" aria-label="青蓝水墨主视觉">
    <div class="river-ink-reveal" aria-hidden="true">
      <img class="river-ink-art" :src="riverArtwork" alt="" fetchpriority="high" />
    </div>
    <div class="river-hero-copy">
      <div class="river-eyebrow">知有边界，想象无界</div>
      <h2 class="river-heading">心有山海，<br />自有<span>知舟。</span></h2>
      <p class="river-description">让知识流动，让想法抵达。</p>
    </div>
    <span class="river-seal" aria-hidden="true">山海</span>
    <div class="river-caption" aria-hidden="true">
      A CURRENT OF IDEAS<ArrowDownRight :size="20" />
    </div>
  </section>
</template>
<style scoped>
.river-hero {
  position: relative;
  min-height: 365px;
  padding: 30px 24px 0;
  isolation: isolate;
}
.river-hero-copy {
  position: relative;
  z-index: 1;
  text-align: center;
}
.river-eyebrow {
  color: var(--text-secondary);
  font-size: 11px;
  letter-spacing: 3px;
}
.river-heading {
  margin: 18px 0 16px;
  font-size: clamp(46px, 4.8vw, 67px);
  line-height: 1.17;
  letter-spacing: -3px;
  font-weight: 500;
}
.river-heading span {
  color: var(--brand);
}
.river-description {
  display: inline-block;
  margin: 0;
  padding: 3px 9px;
  background: color-mix(in srgb, var(--bg) 84%, transparent);
  color: var(--text-secondary);
  font-size: 12px;
  letter-spacing: 0.8px;
}
.river-ink-reveal {
  position: absolute;
  z-index: -1;
  inset: 70px -18px -110px;
  opacity: 0.72;
  pointer-events: none;
}
.river-ink-art {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center 65%;
  filter: var(--hero-art-filter);
}
.river-seal {
  position: absolute;
  right: 32px;
  bottom: 42px;
  padding: 6px 4px;
  border: 1px solid var(--brand);
  writing-mode: vertical-rl;
  color: var(--brand);
  font-family: 'Songti SC', SimSun, serif;
  font-size: 13px;
  letter-spacing: 3px;
}
.river-caption {
  position: absolute;
  right: 32px;
  bottom: 10px;
  display: flex;
  align-items: center;
  gap: 16px;
  color: var(--text-secondary);
  font-size: 8px;
  letter-spacing: 2px;
}
/* 只在允许动态效果时播放，默认样式始终显示完整画面；页面隐藏由外层统一暂停。 */
.river-hero[data-motion='on'] .river-ink-reveal {
  animation: river-reveal 1.1s cubic-bezier(0.22, 0.7, 0.22, 1) both;
}
.river-hero[data-motion='on'] .river-ink-art {
  animation: river-drift 16s ease-in-out infinite alternate;
}
@keyframes river-reveal {
  from {
    clip-path: inset(0 0 0 100%);
  }
  to {
    clip-path: inset(0);
  }
}
@keyframes river-drift {
  from {
    transform: translate3d(-5px, 2px, 0) scale(1);
  }
  to {
    transform: translate3d(7px, -5px, 0) scale(1.025);
  }
}
@media (min-width: 1440px) {
  .river-hero {
    min-height: 410px;
  }
}
@media (max-width: 760px) {
  .river-hero {
    min-height: 330px;
    padding: 24px 20px 0;
  }
  .river-heading {
    font-size: 48px;
    margin-top: 22px;
  }
  .river-eyebrow {
    font-size: 10px;
    letter-spacing: 2px;
  }
  .river-ink-reveal {
    inset: 85px -100px -65px;
    opacity: 0.6;
  }
  .river-seal {
    right: 20px;
    bottom: 30px;
    font-size: 11px;
  }
  .river-caption {
    right: 20px;
    bottom: 0;
    font-size: 7px;
    letter-spacing: 1px;
  }
}
</style>
