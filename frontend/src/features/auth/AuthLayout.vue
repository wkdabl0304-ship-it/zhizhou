<!-- 认证页面外壳：在全幅动态山海上居中组合品牌与表单，复用主题及可清理的动效生命周期。 -->
<script setup lang="ts">
import BrandLogo from '@/shared/components/BrandLogo.vue'
import ThemeMenu from '@/shared/components/ThemeMenu.vue'
import RiverBackdrop from '@/shared/components/RiverBackdrop.vue'
import { useMotionPreference } from '@/shared/composables/useMotionPreference'

const { enabled, visible } = useMotionPreference()
</script>

<template>
  <div class="auth-page" :data-motion="enabled ? 'on' : 'off'" :data-visible="visible">
    <!-- 背景属于整页，覆盖页头、分栏和页脚；表单限宽不再裁切山景。 -->
    <RiverBackdrop :motion="enabled" />
    <header class="auth-header">
      <RouterLink to="/login" class="auth-brand" aria-label="知舟登录首页">
        <BrandLogo :size="41" /><span>知舟<small>ZHIZHOU</small></span>
      </RouterLink>
      <div class="auth-header-end"><ThemeMenu compact /></div>
    </header>
    <main class="auth-main">
      <section class="auth-scene" aria-label="心有山海，自有知舟">
        <div class="auth-editorial">
          <h1>
            <span class="auth-title-line">心有山海，</span><br />
            <span class="auth-title-line auth-title-line--second"
              >自有<span class="auth-title-brand">知舟。</span></span
            >
          </h1>
        </div>
      </section>
      <section class="auth-panel" aria-label="账号认证">
        <div class="auth-panel-inner"><slot /></div>
      </section>
    </main>
  </div>
</template>

<style scoped>
/* 认证页使用自然文档滚动，短屏或注册校验展开时不会截断主操作。 */
.auth-page {
  position: relative;
  isolation: isolate;
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  background: var(--bg);
}
.auth-page :deep(.river-backdrop) {
  opacity: 0.92;
}
.auth-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 25px clamp(24px, 4vw, 64px);
  animation: auth-arrive 850ms cubic-bezier(0.16, 1, 0.3, 1) both;
}
.auth-brand {
  display: flex;
  align-items: center;
  gap: 11px;
  color: var(--text);
  text-decoration: none;
}
.auth-brand > span {
  font-size: 24px;
  letter-spacing: 4px;
  line-height: 1.3;
}
.auth-brand small {
  display: block;
  margin-top: 3px;
  font-size: 9px;
  letter-spacing: 3px;
  color: var(--text-muted);
}
.auth-header-end {
  display: flex;
  align-items: center;
  gap: 22px;
  color: var(--text-muted);
  font-size: 11px;
  letter-spacing: 1px;
}
.auth-main {
  position: relative;
  isolation: isolate;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 380px);
  align-items: center;
  column-gap: clamp(40px, 6vw, 104px);
  flex: 1;
  width: 100%;
  max-width: 1000px;
  margin: 0 auto;
  padding: 48px 32px 72px;
}
/* 只给正文限宽，背景仍铺满；共享的柔和底光保证可读性，不形成有边缘的白色面板。 */
.auth-main::before {
  content: '';
  position: absolute;
  z-index: -1;
  inset: 0;
  background: radial-gradient(
    ellipse at 52% 44%,
    color-mix(in srgb, var(--bg) 88%, transparent),
    color-mix(in srgb, var(--bg) 66%, transparent) 46%,
    transparent 74%
  );
  pointer-events: none;
}
.auth-scene {
  justify-self: end;
  width: 100%;
  max-width: 400px;
  min-width: 0;
}
.auth-editorial {
  position: relative;
  animation: auth-arrive 1100ms cubic-bezier(0.16, 1, 0.3, 1) 80ms both;
}
.auth-editorial h1 {
  margin: 0;
  font-family: 'Songti SC', 'STSong', 'SimSun', serif;
  font-size: clamp(42px, 4vw, 68px);
  font-weight: 400;
  line-height: 1.45;
  letter-spacing: 3px;
}
.auth-title-line {
  display: inline-block;
  animation: auth-title-float 6s ease-in-out -1s infinite alternate;
}
.auth-title-line--second {
  animation-delay: -4s;
}
.auth-title-brand {
  position: relative;
  display: inline-block;
  color: var(--brand);
}
/* 强调水线独立于文字缓动，不移动输入框或改变表单排版。 */
.auth-title-brand::after {
  content: '';
  position: absolute;
  inset: auto 0 0.08em;
  height: 2px;
  border-radius: 50%;
  background: linear-gradient(90deg, transparent, var(--brand), transparent);
  animation: auth-waterline 4s ease-in-out -2s infinite alternate;
}
.auth-panel {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 0;
}
.auth-panel-inner {
  width: 100%;
  max-width: 380px;
  animation: auth-arrive 1000ms cubic-bezier(0.16, 1, 0.3, 1) 160ms both;
}
@keyframes auth-arrive {
  from {
    opacity: 0;
    transform: translate3d(0, 16px, 0);
  }
  to {
    opacity: 1;
    transform: translate3d(0, 0, 0);
  }
}
@keyframes auth-title-float {
  from {
    transform: translate3d(0, 2px, 0);
  }
  to {
    transform: translate3d(0, -4px, 0);
  }
}
@keyframes auth-waterline {
  from {
    opacity: 0.35;
    transform: scaleX(0.65);
  }
  to {
    opacity: 0.9;
    transform: scaleX(1.04);
  }
}
/* 后台保留动画进度；减少动态效果时去掉入场和缓动，内容直接完整呈现。 */
.auth-page[data-visible='false'] :deep(*),
.auth-page[data-visible='false'] :deep(*::before),
.auth-page[data-visible='false'] :deep(*::after) {
  animation-play-state: paused !important;
}
.auth-page[data-motion='off'] :deep(*),
.auth-page[data-motion='off'] :deep(*::before),
.auth-page[data-motion='off'] :deep(*::after) {
  animation: none !important;
  transition: none !important;
}
@media (max-width: 760px) {
  .auth-header {
    padding: 22px 24px;
  }
  .auth-main {
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 24px;
    max-width: 480px;
    padding: 12px 26px 40px;
  }
  .auth-scene {
    max-width: none;
    min-height: 130px;
    padding: 6px 0 16px;
  }
  .auth-editorial h1 {
    margin: 12px 0 0;
    font-size: clamp(26px, 6vw, 38px);
    letter-spacing: 1px;
  }
  .auth-editorial h1 br {
    display: none;
  }
  .auth-panel {
    flex: 1;
  }
  .auth-panel-inner {
    max-width: 400px;
  }
}
</style>
