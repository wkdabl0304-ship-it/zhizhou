<!-- 首页标题区：组合已选现代宋体与山海标记；全幅水墨由主区域的 RiverBackdrop 独立承载。 -->
<script setup lang="ts">
import WelcomeHeading from './WelcomeHeading.vue'
</script>
<template>
  <section class="river-hero" aria-label="青蓝水墨主视觉">
    <div class="river-hero-copy">
      <WelcomeHeading />
    </div>
    <span class="river-seal" aria-hidden="true">山海</span>
  </section>
</template>
<style scoped>
.river-hero {
  position: relative;
  min-height: 230px;
  padding: 30px 24px 0;
}
.river-hero-copy {
  position: relative;
  z-index: 1;
  text-align: center;
}
.river-seal {
  position: absolute;
  right: 32px;
  bottom: 42px;
  padding: 6px 4px;
  border: 1px solid var(--accent);
  writing-mode: vertical-rl;
  color: var(--accent);
  background: color-mix(in srgb, var(--accent-soft) 75%, transparent);
  font-family: 'Songti SC', SimSun, serif;
  font-size: 13px;
  letter-spacing: 3px;
}
@media (min-width: 1440px) {
  .river-hero {
    min-height: 260px;
  }
}
@media (max-width: 760px) {
  .river-hero {
    min-height: 190px;
    padding: 24px 20px 0;
  }
  .river-seal {
    right: 20px;
    bottom: 30px;
    font-size: 11px;
  }
}
</style>
