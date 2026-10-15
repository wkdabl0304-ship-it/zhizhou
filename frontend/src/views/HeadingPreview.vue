<!-- 开发标题比较页：复用正式首页与局部主题，试验文字方案，不读写正式聊天、主题或持久化存储。 -->
<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowLeft, ArrowUpRight, Moon, PanelLeft, Plus, Sun } from '@lucide/vue'
import { TabsContent, TabsList, TabsRoot, TabsTrigger } from 'reka-ui'
import BrandLogo from '@/components/BrandLogo.vue'
import HeadingStudy from '@/components/brand/HeadingStudy.vue'
import ChatWelcome from '@/components/chat/ChatWelcome.vue'

const options = [
  {
    id: 'original',
    number: '00',
    name: '已提交原版',
    detail: '67px · 中等字重 · 均衡两行',
    description: '青蓝水墨首次采用时保存的排版，作为历史比较基准。',
  },
  {
    id: 'bold',
    number: '01',
    name: '大字重排',
    detail: '82px · 厚重黑体 · 紧凑行距',
    description: '保留两行结构，用更大的字与更紧的节奏增强力量感。',
  },
  {
    id: 'focus',
    number: '02',
    name: '知舟聚焦',
    detail: '110px 品牌名 · 大小层次 · 单点聚焦',
    description: '把前半句收成引言，让“知舟”成为第一眼看到的视觉中心。',
  },
  {
    id: 'serif',
    number: '03',
    name: '现代宋体 · 已采用',
    detail: '74px · 宋体笔锋 · 疏朗字距',
    description: '让文字和水墨更接近，安静但有辨识度。使用本机宋体，跨设备字形略有差异。',
  },
] as const
type Variant = (typeof options)[number]['id']
const variant = ref<Variant>('serif')
const theme = ref<'light' | 'dark'>('light')
const draft = ref('')
const sent = ref('')
const surface = ref<HTMLElement>()
// 说明面板与当前标签同步；正式首页与已选宋体复用组件，其他方案仍留在开发页。
const active = computed(() => options.find((option) => option.id === variant.value)!)

/** 只接受比较列表内的方案；切换不销毁输入框，保留尚未发送的草稿。 */
function selectVariant(value: unknown): void {
  const match = options.find((option) => option.id === value)
  if (match) variant.value = match.id
}
/** 输入仅用于查看首页状态和焦点反馈，不创建正式会话，也不跳离当前比较画面。 */
function previewSend(text: string): void {
  sent.value = `已在本页试发：${text}。这是标题预览，不生成 AI 回复。`
}
/** 恢复局部空白首页，便于继续查看标题，不影响应用中的会话。 */
function resetPreview(): void {
  draft.value = ''
  sent.value = ''
}
</script>
<template>
  <div class="heading-lab">
    <TabsRoot :model-value="variant" @update:model-value="selectVariant">
      <header class="study-toolbar">
        <div class="study-intro">
          <RouterLink to="/" aria-label="返回正式首页"><ArrowLeft :size="18" /></RouterLink>
          <div>
            <h1>青蓝水墨 · 标题探索</h1>
            <p>只比较文字。文案、山海背景与输入区保持一致。</p>
          </div>
        </div>
        <RouterLink class="study-baseline" to="/"
          >查看已采用的现代宋体<ArrowUpRight :size="13"
        /></RouterLink>
      </header>
      <div class="study-controls">
        <TabsList class="study-tabs" aria-label="首页标题方案">
          <TabsTrigger
            v-for="option in options"
            :key="option.id"
            :value="option.id"
            class="study-tab"
          >
            <small>{{ option.number }}</small
            >{{ option.name }}
          </TabsTrigger>
        </TabsList>
        <div class="study-themes" role="group" aria-label="局部预览主题">
          <button
            type="button"
            aria-label="预览浅色"
            :aria-pressed="theme === 'light'"
            @click="theme = 'light'"
          >
            <Sun :size="16" />
          </button>
          <button
            type="button"
            aria-label="预览深色"
            :aria-pressed="theme === 'dark'"
            @click="theme = 'dark'"
          >
            <Moon :size="16" />
          </button>
        </div>
      </div>
      <TabsContent :value="variant" class="study-panel">
        <div class="study-note" aria-live="polite">
          <strong>{{ active.detail }}</strong
          ><span>{{ active.description }}</span>
        </div>
        <section
          ref="surface"
          class="heading-surface theme-scope"
          :data-theme="theme"
          :aria-label="`${active.name}首页预览`"
        >
          <aside class="study-sidebar" aria-label="首页外壳预览">
            <div class="study-wordmark">
              <BrandLogo :size="39" /><span>知舟<small>ZHIZHOU</small></span
              ><PanelLeft :size="17" />
            </div>
            <button class="study-new" type="button" @click="resetPreview">
              <Plus :size="17" />开启新对话
            </button>
            <p class="study-history-label">最近对话 · 外壳示意</p>
            <p class="study-history">新员工第一周入职清单</p>
            <p class="study-history">产品需求评审准备</p>
            <div class="study-sidebar-foot"><BrandLogo :size="22" /><span>让知识流动</span></div>
          </aside>
          <main class="study-main">
            <div class="study-app-header">
              <span>此刻，思考启程</span><small>KNOWLEDGE IN FLOW</small>
            </div>
            <div class="study-home">
              <ChatWelcome
                v-model="draft"
                :motion="false"
                :tooltip-portal-target="surface"
                @send="previewSend"
              >
                <template #heading><HeadingStudy :variant="variant" /></template>
              </ChatWelcome>
            </div>
            <p v-if="sent" class="study-sent" role="status">{{ sent }}</p>
          </main>
        </section>
        <footer class="study-footer">
          <span>现代宋体已应用到正式首页，其他排版保留供比较。动效固定关闭，便于比较字形。</span
          ><RouterLink to="/dev/brand">查看品牌探索</RouterLink>
        </footer>
      </TabsContent>
    </TabsRoot>
  </div>
</template>
<style scoped>
.heading-lab {
  color-scheme: light;
  background: #f8faf9;
  color: #203b45;
  min-height: 100dvh;
}
.study-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  padding: 22px 30px 14px;
}
.study-intro {
  display: flex;
  align-items: center;
  gap: 15px;
}
.study-intro > a {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border: 1px solid #d1dfe2;
  border-radius: 50%;
}
.study-intro h1 {
  margin: 0;
  font-size: 18px;
  letter-spacing: 1px;
}
.study-intro p {
  margin: 4px 0 0;
  font-size: 11px;
  color: #526c75;
}
.study-baseline {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 11px;
  color: #526c75;
}
.study-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 30px 14px;
}
.study-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.study-tab {
  display: flex;
  align-items: center;
  gap: 9px;
  border: 1px solid #d1dfe2;
  border-radius: 7px;
  padding: 9px 14px;
  background: transparent;
  color: #4b6973;
  font-size: 12px;
}
.study-tab small {
  font-size: 9px;
  opacity: 0.7;
}
.study-tab[data-state='active'] {
  border-color: #167c91;
  background: #167c91;
  color: white;
}
.study-themes {
  display: flex;
  gap: 3px;
}
.study-themes button {
  display: grid;
  place-items: center;
  width: 33px;
  height: 33px;
  border: 1px solid #d1dfe2;
  border-radius: 6px;
  background: transparent;
  color: #526c75;
}
.study-themes button[aria-pressed='true'] {
  background: #dfebed;
  color: #142c3e;
}
.study-note {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
  padding: 12px 30px;
  border-top: 1px solid #d1dfe2;
  font-size: 11px;
  color: #526c75;
}
.study-note strong {
  color: #203b45;
  font-weight: 600;
}
.heading-surface {
  display: grid;
  /* 水墨在窄屏主动延伸以保持构图，只在应用预览边界裁切，避免撑宽整页。 */
  overflow: clip;
  grid-template-columns: 260px minmax(0, 1fr);
  min-height: max(760px, calc(100dvh - 208px));
  border-block: 1px solid var(--border-strong);
  background: var(--bg);
  color: var(--text);
}
.study-sidebar {
  display: flex;
  flex-direction: column;
  padding: 28px 18px 20px;
  background: var(--sidebar-bg);
  border-right: 1px solid var(--border-strong);
}
.study-wordmark {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 36px;
}
.study-wordmark > span {
  font-size: 22px;
  letter-spacing: 4px;
  font-weight: 500;
}
.study-wordmark small {
  display: block;
  font-size: 9px;
  letter-spacing: 3px;
  color: var(--text-muted);
}
.study-wordmark > svg {
  margin-left: auto;
  color: var(--text-secondary);
}
.study-new {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 11px;
  border: 1px solid var(--border-strong);
  border-radius: 30px;
  background: transparent;
  color: var(--text);
  font-size: 12px;
}
.study-new:hover {
  background: var(--surface-hover);
}
.study-history-label {
  margin: 34px 12px 10px;
  color: var(--text-muted);
  font-size: 10px;
}
.study-history {
  margin: 0;
  padding: 12px;
  color: var(--text-secondary);
  font-size: 12px;
}
.study-sidebar-foot {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: auto 12px 0;
  color: var(--text-secondary);
  font-size: 11px;
}
.study-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.study-app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  min-height: 64px;
  padding: 14px 30px;
  font-size: 12px;
  color: var(--text-secondary);
}
.study-app-header small {
  font-size: 9px;
  letter-spacing: 1.5px;
  color: var(--text-muted);
}
.study-home {
  display: flex;
  flex: 1;
  min-width: 0;
}
.study-sent {
  margin: 0 24px 18px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text-secondary);
  font-size: 12px;
  overflow-wrap: anywhere;
}
.study-footer {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  padding: 15px 30px;
  font-size: 10px;
  color: #526c75;
}
.study-footer a {
  white-space: nowrap;
  text-decoration: underline;
}
@media (max-width: 760px) {
  .study-toolbar {
    padding: 18px 18px 14px;
  }
  .study-baseline {
    display: none;
  }
  .study-intro {
    gap: 10px;
  }
  .study-intro h1 {
    font-size: 16px;
  }
  .study-intro p {
    font-size: 10px;
  }
  .study-controls {
    align-items: flex-start;
    padding: 0 18px 12px;
    gap: 9px;
  }
  .study-tabs {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    flex: 1;
  }
  .study-tab {
    padding: 9px 10px;
    gap: 6px;
    font-size: 11px;
  }
  .study-note {
    padding: 12px 18px;
    font-size: 10px;
  }
  .heading-surface {
    grid-template-columns: minmax(0, 1fr);
    min-height: 740px;
  }
  .study-sidebar {
    display: none;
  }
  .study-app-header {
    padding: 14px 20px;
  }
  .study-app-header small {
    display: none;
  }
  .study-footer {
    padding: 14px 18px;
    font-size: 9px;
  }
}
</style>
