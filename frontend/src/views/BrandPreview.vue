<!-- 开发品牌探索页：独立切换视觉、页面和主题，展示真实 DOM 原型与原创 Logo 尺寸板。 -->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowLeft, ArrowUpRight, Moon, Pause, Play, Sun } from '@lucide/vue'
import { TabsRoot, TabsList, TabsTrigger, TabsContent } from 'reka-ui'
import BrandMark from '@/components/brand/BrandMark.vue'
import BrandScene from '@/components/brand/BrandScene.vue'
import {
  brandDesigns,
  isBrandId,
  type BrandId,
  type BrandPage,
  type BrandTheme,
} from '@/components/brand/designs'
import { useMotionPreference } from '@/composables/useMotionPreference'

const variant = ref<BrandId>('paper')
const theme = ref<BrandTheme>('light')
const page = ref<BrandPage>('home')
const { requested, reduced, visible, enabled } = useMotionPreference()
// 受控标签只允许配置内的标识，未定义输入不改变当前方案。
const design = computed(() => brandDesigns.find((item) => item.id === variant.value)!)
const logoSizes = [16, 24, 48, 128]

/** 方案切换只更新局部展示变量，不修改正式页面的配色、聊天记录或存储。 */
function selectVariant(value: unknown): void {
  if (isBrandId(value)) variant.value = value
}
</script>

<template>
  <div class="brand-lab">
    <TabsRoot :model-value="variant" @update:model-value="selectVariant">
      <header class="lab-header">
        <div class="lab-heading">
          <RouterLink to="/" aria-label="返回正式聊天页"><ArrowLeft :size="18" /></RouterLink>
          <div>
            <h1>知舟 · 品牌探索</h1>
            <p>东方笔意，现代思考。选择一种你喜欢的感觉。</p>
          </div>
        </div>
        <span class="lab-dev-label">DESIGN STUDY / 2026</span>
      </header>
      <div class="lab-toolbar">
        <TabsList class="lab-variants" aria-label="视觉方案"
          ><TabsTrigger
            v-for="item in brandDesigns"
            :key="item.id"
            :value="item.id"
            class="lab-variant"
            ><span>{{ item.number }}</span
            >{{ item.name }}</TabsTrigger
          ></TabsList
        >
        <div class="lab-options">
          <div class="lab-segment" role="group" aria-label="预览页面">
            <button type="button" :aria-pressed="page === 'home'" @click="page = 'home'">
              首页</button
            ><button type="button" :aria-pressed="page === 'chat'" @click="page = 'chat'">
              对话
            </button>
          </div>
          <div class="lab-segment" role="group" aria-label="原型主题">
            <button
              type="button"
              aria-label="原型浅色"
              :aria-pressed="theme === 'light'"
              @click="theme = 'light'"
            >
              <Sun :size="15" /></button
            ><button
              type="button"
              aria-label="原型深色"
              :aria-pressed="theme === 'dark'"
              @click="theme = 'dark'"
            >
              <Moon :size="15" />
            </button>
          </div>
          <button
            type="button"
            class="lab-motion"
            :aria-pressed="requested"
            @click="requested = !requested"
          >
            <Pause v-if="requested" :size="14" /><Play v-else :size="14" /><span>{{
              reduced ? '系统减少动效' : requested ? '动效开启' : '动效关闭'
            }}</span>
          </button>
        </div>
      </div>
      <TabsContent :value="variant" class="lab-panel"
        ><BrandScene
          :design="design"
          :theme="theme"
          v-model:page="page"
          :motion="enabled"
          :visible="visible"
      /></TabsContent>
    </TabsRoot>
    <section
      class="lab-identity"
      :style="{ '--b-accent': design.palette[2]?.color }"
      aria-label="Logo 草案与色卡"
    >
      <div class="lab-identity-intro">
        <span class="lab-overline">{{ design.english }}</span>
        <h2>{{ design.name }}</h2>
        <p>{{ design.description }}</p>
        <div class="lab-swatches">
          <div v-for="color in design.palette" :key="color.name">
            <i :style="{ background: color.color }" /><span
              >{{ color.name }}<small>{{ color.color }}</small></span
            >
          </div>
        </div>
      </div>
      <div class="lab-logo-board">
        <div class="lab-logo-title">
          <h3>舟与航迹 / Logo 草案</h3>
          <span>同一形状，不同尺度</span>
        </div>
        <div class="lab-logo-sizes">
          <div v-for="size in logoSizes" :key="size">
            <BrandMark :variant="variant" :size="size" :decorative="false" /><span
              >{{ size }}px</span
            >
          </div>
        </div>
        <p>{{ design.logoIdea }}</p>
        <div class="lab-logo-tones">
          <span><BrandMark :variant="variant" :size="30" tone="brand" />彩色</span
          ><span><BrandMark :variant="variant" :size="30" tone="ink" />单色</span
          ><span class="lab-reverse"
            ><BrandMark :variant="variant" :size="30" tone="reverse" />反白</span
          >
        </div>
      </div>
    </section>
    <footer class="lab-footer">
      <span>三种视觉共用独立演示会话。切换方案可比较同一段内容。</span
      ><RouterLink to="/dev/ui">基础组件预览<ArrowUpRight :size="13" /></RouterLink>
    </footer>
  </div>
</template>

<style scoped>
/* 外层控制面板固定使用中性配色，不跟随正式主题，也不污染原型内部的品牌色。 */
.brand-lab {
  color-scheme: light;
  min-height: 100dvh;
  padding: 23px 28px 24px;
  color: #252b29;
  background: #e9ece9;
  font-family: var(--font-sans);
}
.lab-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 21px;
}
.lab-heading {
  display: flex;
  align-items: center;
  gap: 17px;
}
.lab-heading > a {
  display: grid;
  place-items: center;
  width: 31px;
  height: 35px;
  color: #414b45;
}
.lab-heading h1 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 1px;
}
.lab-heading p {
  margin: 2px 0 0;
  font-size: 11px;
  color: #5b675f;
}
.lab-dev-label {
  color: #67746b;
  font-size: 9px;
  letter-spacing: 2px;
}
.lab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}
.lab-variants {
  display: flex;
  gap: 5px;
  min-width: 0;
}
.lab-variant {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  min-height: 35px;
  padding: 8px 14px;
  border: 1px solid transparent;
  border-radius: 5px;
  background: transparent;
  color: #546158;
  font-size: 11px;
}
.lab-variant > span {
  color: #69776d;
  font-size: 9px;
  font-family: var(--font-mono);
}
.lab-variant[data-state='active'] {
  border-color: #d3d9d3;
  background: #f9faf8;
  box-shadow: 0 1px 4px rgb(0 0 0 / 3%);
  color: #1d2620;
}
.lab-options {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 11px;
}
.lab-segment {
  display: inline-flex;
  padding: 2px;
  border: 1px solid #ced5cd;
  border-radius: 5px;
}
.lab-segment button {
  display: grid;
  place-items: center;
  min-width: 31px;
  height: 27px;
  padding: 4px 9px;
  border: 0;
  border-radius: 3px;
  background: transparent;
  color: #526056;
  font-size: 10px;
}
.lab-segment button[aria-pressed='true'] {
  background: #f9faf8;
  color: #1d2620;
  box-shadow: 0 1px 3px rgb(0 0 0 / 5%);
}
.lab-motion {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-width: 86px;
  padding: 5px 0;
  border: 0;
  background: transparent;
  font-size: 10px;
  color: #536258;
}
.lab-panel {
  outline-offset: 5px;
}
.lab-identity {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.25fr);
  gap: 55px;
  padding: 50px 36px 32px;
  margin-top: 18px;
  border: 1px solid #d7ddd5;
  background: #f7f8f4;
}
.lab-overline {
  font-size: 9px;
  letter-spacing: 2px;
  color: #657366;
}
.lab-identity h2 {
  margin: 13px 0 10px;
  font-size: 27px;
  font-weight: 500;
  letter-spacing: -1px;
}
.lab-identity-intro p {
  margin: 0;
  font-size: 12px;
  line-height: 1.9;
  color: #5a685d;
}
.lab-swatches {
  display: flex;
  gap: 24px;
  margin-top: 30px;
}
.lab-swatches > div {
  display: flex;
  align-items: center;
  gap: 9px;
}
.lab-swatches i {
  width: 28px;
  height: 35px;
  border: 1px solid rgb(0 0 0 / 10%);
  border-radius: 1px;
}
.lab-swatches span {
  display: flex;
  flex-direction: column;
  font-size: 11px;
}
.lab-swatches small {
  color: #677468;
  font-size: 9px;
}
.lab-logo-board {
  color: #171714;
}
.lab-logo-title {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}
.lab-logo-title h3 {
  margin: 0;
  font-size: 12px;
  font-weight: 500;
}
.lab-logo-title > span {
  color: #687469;
  font-size: 10px;
}
.lab-logo-sizes {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
  padding: 17px 10px 20px;
  border-bottom: 1px solid #d9dfd6;
}
.lab-logo-sizes > div {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  gap: 7px;
}
.lab-logo-sizes > div > span:last-child {
  color: #6a766c;
  font-size: 9px;
}
.lab-logo-board > p {
  margin: 15px 0;
  color: #5a685d;
  font-size: 11px;
}
.lab-logo-tones {
  display: flex;
  gap: 10px;
}
.lab-logo-tones > span {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 7px 12px;
  border: 1px solid #d7ddd3;
  font-size: 10px;
}
.lab-logo-tones > .lab-reverse {
  border-color: #202620;
  background: #202620;
  color: #f7f7f3;
}
.lab-footer {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 22px 4px 0;
  color: #5e6c61;
  font-size: 10px;
}
.lab-footer a {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: inherit;
  text-decoration: none;
  white-space: nowrap;
}
.brand-lab :focus-visible {
  outline-color: #37624a;
}
@media (max-width: 1150px) {
  .lab-identity {
    gap: 25px;
    padding-inline: 24px;
  }
  .lab-swatches {
    gap: 15px;
  }
}
@media (max-width: 760px) {
  .brand-lab {
    padding: 17px 12px;
  }
  .lab-header {
    margin-bottom: 16px;
  }
  .lab-heading {
    gap: 6px;
  }
  .lab-heading h1 {
    font-size: 15px;
  }
  .lab-heading p {
    max-width: 270px;
    font-size: 10px;
  }
  .lab-dev-label {
    display: none;
  }
  .lab-toolbar {
    gap: 10px;
  }
  .lab-variants {
    width: 100%;
    gap: 3px;
  }
  .lab-variant {
    flex: 1;
    gap: 5px;
    min-height: 39px;
    padding: 7px 5px;
    font-size: 10px;
  }
  .lab-variant > span {
    font-size: 8px;
  }
  .lab-options {
    width: 100%;
    justify-content: flex-end;
    gap: 9px;
  }
  .lab-identity {
    grid-template-columns: minmax(0, 1fr);
    gap: 34px;
    padding: 30px 20px;
  }
  .lab-identity h2 {
    font-size: 24px;
  }
  .lab-swatches {
    flex-wrap: wrap;
    gap: 18px;
    margin-top: 22px;
  }
  .lab-logo-title {
    flex-wrap: wrap;
  }
  .lab-logo-sizes {
    gap: 10px;
    padding-inline: 0;
  }
  .lab-logo-tones {
    flex-wrap: wrap;
  }
  .lab-logo-tones > span {
    gap: 7px;
    padding: 6px 9px;
  }
  .lab-footer {
    flex-wrap: wrap;
    font-size: 9px;
  }
}
@media (pointer: coarse) {
  .lab-segment button,
  .lab-motion,
  .lab-variant {
    min-height: 44px;
  }
}
</style>
