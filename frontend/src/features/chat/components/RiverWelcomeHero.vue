<!-- 首页标题区：组合已选现代宋体与山海标记；全幅水墨由主区域的 RiverBackdrop 独立承载。 -->
<script setup lang="ts">
import { ArrowDownRight } from '@lucide/vue'
import WelcomeHeading from './WelcomeHeading.vue'
</script>
<template>
  <section class="river-hero" aria-label="青蓝水墨主视觉">
    <div class="river-hero-copy">
      <div class="river-eyebrow">知有边界，想象无界</div>
      <WelcomeHeading />
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
.river-description {
  display: inline-block;
  margin: 0;
  padding: 3px 9px;
  background: color-mix(in srgb, var(--bg) 84%, transparent);
  color: var(--text-secondary);
  font-size: 12px;
  letter-spacing: 0.8px;
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
  .river-eyebrow {
    font-size: 10px;
    letter-spacing: 2px;
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
