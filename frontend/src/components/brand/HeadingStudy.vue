<!-- 标题探索模块：保留原版与候选的比较，已选现代宋体直接复用正式标题组件。 -->
<script setup lang="ts">
import WelcomeHeading from '@/components/chat/WelcomeHeading.vue'
defineProps<{ variant: 'original' | 'bold' | 'focus' | 'serif' }>()
</script>
<template>
  <WelcomeHeading v-if="variant === 'serif'" />
  <h2 v-else-if="variant === 'focus'" class="study-heading study-focus">
    <span class="focus-intro">心有山海，自有</span>
    <span class="focus-name">知舟<span class="focus-stop">。</span></span>
  </h2>
  <h2 v-else class="study-heading" :class="`study-${variant}`">
    心有山海，<br />自有<span class="study-brand">知舟。</span>
  </h2>
</template>
<style scoped>
/* 三款标题保留相近的占位空间，突出字形差异，避免改变整体首页构图。 */
.study-heading {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-height: 157px;
  margin: 18px 0 16px;
  color: var(--text);
}
.study-brand {
  color: var(--brand);
}
.study-original {
  display: block;
  min-height: 0;
  font-size: clamp(46px, 4.8vw, 67px);
  line-height: 1.17;
  letter-spacing: -3px;
  font-weight: 500;
}
.study-bold {
  display: block;
  font-size: clamp(60px, 5.8vw, 82px);
  font-weight: 800;
  letter-spacing: -4px;
  line-height: 1.02;
}
.study-focus {
  align-items: center;
  gap: 4px;
  line-height: 1;
}
.focus-intro {
  padding-left: 5px;
  font-size: 22px;
  font-weight: 500;
  letter-spacing: 5px;
}
.focus-name {
  position: relative;
  color: var(--brand);
  font-size: clamp(88px, 7.7vw, 110px);
  font-weight: 800;
  letter-spacing: -7px;
}
.focus-stop {
  position: absolute;
  bottom: 8px;
  font-size: 50px;
}
@media (max-width: 760px) {
  .study-heading {
    margin-top: 22px;
    min-height: 113px;
  }
  .study-bold {
    font-size: 55px;
    letter-spacing: -3px;
  }
  .focus-intro {
    font-size: 15px;
    letter-spacing: 3px;
  }
  .focus-name {
    font-size: 84px;
    letter-spacing: -5px;
  }
  .focus-stop {
    font-size: 34px;
    bottom: 6px;
  }
  .study-original {
    min-height: 0;
    font-size: 48px;
  }
}
</style>
