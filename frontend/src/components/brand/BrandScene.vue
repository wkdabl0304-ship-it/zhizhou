<!-- 品牌应用原型：三种设计共用安全消息与真实输入行为，视觉和演示状态与正式聊天页隔离。 -->
<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import {
  ArrowDownRight,
  ArrowUpRight,
  Compass,
  CornerUpLeft,
  Menu,
  MessageSquare,
  Plus,
  SquarePen,
  X,
} from '@lucide/vue'
import {
  DialogRoot,
  DialogTrigger,
  DialogPortal,
  DialogOverlay,
  DialogContent,
  DialogTitle,
  DialogDescription,
  DialogClose,
} from 'reka-ui'
import { useMediaQuery } from '@/composables/useMediaQuery'
import ChatComposer from '@/components/chat/ChatComposer.vue'
import BrandMark from './BrandMark.vue'
import type { BrandDesign, BrandPage, BrandTheme } from './designs'
import { useBrandPrototype } from './useBrandPrototype'

const props = defineProps<{
  design: BrandDesign
  theme: BrandTheme
  page: BrandPage
  motion: boolean
  visible: boolean
}>()
const emit = defineEmits<{ 'update:page': [page: BrandPage] }>()
const {
  conversations,
  activeId,
  activeConversation,
  page: currentPage,
  draft,
  scrollArea,
  startNew,
  selectConversation,
  setPage,
  send,
} = useBrandPrototype()
const composer = ref<InstanceType<typeof ChatComposer>>()
const narrow = useMediaQuery('(max-width: 760px)')
const drawerOpen = ref(false)
const portalTarget = ref<HTMLElement>()
const sceneTitle = ref<HTMLElement>()
const suggestionTitles = ['梳理一个新想法', '准备一份项目周报', '规划下一步工作']

// 工具栏的页面状态是可控输入；内部导航通过事件保持工具栏同步。
watch(() => props.page, setPage, { immediate: true })
watch(currentPage, (value) => emit('update:page', value))
// 切回宽屏时彻底卸载模态内容，保留 Reka 的清理与焦点恢复行为。
watch(narrow, (value) => {
  if (!value) drawerOpen.value = false
})

/** 选择会话或返回首页，同时关闭移动侧栏，不将草稿带入其他会话。 */
function navigate(id?: string): void {
  if (id) selectConversation(id)
  else startNew()
  drawerOpen.value = false
}

/** 示例只填入输入框，保留用户编辑和发送的决定权。 */
async function fill(text: string): Promise<void> {
  draft.value = text
  await nextTick()
  composer.value?.focus()
}

/** 在首页切换为对话页之后重新聚焦新输入实例，维持连续输入体验。 */
async function submit(text: string): Promise<void> {
  send(text)
  await nextTick()
  composer.value?.focus()
}

/** 断点切换会移除触发器，此时将焦点送往仍存在的页头。 */
function restoreFocus(event: Event): void {
  if (!narrow.value) {
    event.preventDefault()
    sceneTitle.value?.focus()
  }
}
</script>

<template>
  <div
    ref="portalTarget"
    class="brand-surface"
    :class="`brand-${design.id}`"
    :data-theme="theme"
    :data-motion="motion ? 'on' : 'off'"
    :data-visible="visible"
    :data-view="currentPage"
  >
    <div class="brand-app">
      <aside v-if="!narrow" class="b-sidebar" aria-label="品牌原型导航">
        <div class="b-wordmark">
          <BrandMark :variant="design.id" :size="39" /><span>知舟<small>ZHIZHOU</small></span>
        </div>
        <button type="button" class="b-new" @click="navigate()">
          <Plus :size="17" /><span>开启新对话</span><ArrowUpRight :size="15" />
        </button>
        <div class="b-nav-heading">思考的足迹<span>HISTORY</span></div>
        <nav class="b-history" aria-label="品牌演示会话">
          <button
            v-for="conversation in conversations"
            :key="conversation.id"
            type="button"
            class="b-history-item"
            :class="{ 'is-current': activeId === conversation.id && currentPage === 'chat' }"
            :aria-current="
              activeId === conversation.id && currentPage === 'chat' ? 'true' : undefined
            "
            @click="navigate(conversation.id)"
          >
            <MessageSquare :size="14" /><span>{{ conversation.title }}</span>
          </button>
        </nav>
        <div class="b-sidebar-bottom">
          <BrandMark :variant="design.id" :size="64" class="b-sidebar-watermark" />
          <p>知识有岸<br />探索无界</p>
          <div class="b-person">
            <span>舟</span>
            <div>知舟工作空间<small>为每一个好想法，找到方向。</small></div>
            <span class="b-online" />
          </div>
        </div>
      </aside>
      <main class="b-main">
        <header class="b-header">
          <div class="b-header-left">
            <DialogRoot v-if="narrow" v-model:open="drawerOpen"
              ><DialogTrigger as-child
                ><button type="button" class="b-icon-button" aria-label="打开品牌侧栏">
                  <Menu :size="20" /></button></DialogTrigger
              ><DialogPortal :to="portalTarget"
                ><DialogOverlay class="b-drawer-overlay" /><DialogContent
                  class="b-drawer b-sidebar"
                  @close-auto-focus="restoreFocus"
                  ><DialogTitle class="sr-only">品牌演示会话</DialogTitle
                  ><DialogDescription class="sr-only">选择样例会话或开启新对话。</DialogDescription>
                  <div class="b-wordmark">
                    <BrandMark :variant="design.id" :size="38" /><span
                      >知舟<small>ZHIZHOU</small></span
                    >
                  </div>
                  <button type="button" class="b-new" @click="navigate()">
                    <Plus :size="17" />开启新对话
                  </button>
                  <nav class="b-history" aria-label="窄屏品牌演示会话">
                    <button
                      v-for="conversation in conversations"
                      :key="conversation.id"
                      type="button"
                      class="b-history-item"
                      @click="navigate(conversation.id)"
                    >
                      {{ conversation.title }}
                    </button>
                  </nav>
                  <DialogClose as-child
                    ><button
                      type="button"
                      class="b-icon-button b-drawer-close"
                      aria-label="关闭品牌侧栏"
                    >
                      <X :size="18" /></button></DialogClose></DialogContent></DialogPortal
            ></DialogRoot>
            <span class="b-header-index">{{ design.number }} /</span>
            <h2 ref="sceneTitle" tabindex="-1">
              {{ currentPage === 'chat' ? activeConversation?.title : '此刻，思考启程' }}
            </h2>
          </div>
          <span class="b-edition">{{
            design.id === 'paper'
              ? '东方笔意 · 自在探索'
              : design.id === 'river'
                ? 'KNOWLEDGE IN FLOW'
                : 'A SPACE FOR THOUGHT'
          }}</span
          ><button
            v-if="currentPage === 'chat'"
            type="button"
            class="b-icon-button"
            aria-label="返回品牌首页"
            @click="navigate()"
          >
            <SquarePen :size="18" />
          </button>
        </header>
        <div v-if="currentPage === 'home'" class="b-home">
          <section :key="design.id" class="b-hero" aria-label="品牌首页主视觉">
            <div class="b-ink-reveal" aria-hidden="true">
              <img class="b-ink-art" :src="design.artwork" alt="" />
            </div>
            <div class="b-hero-copy">
              <div class="b-eyebrow">
                <span />{{
                  design.id === 'paper'
                    ? '每一个好想法，都值得启航'
                    : design.id === 'river'
                      ? '知有边界，想象无界'
                      : '知舟 / A NEW WAY TO THINK'
                }}
              </div>
              <h3 v-if="design.id === 'paper'" class="b-hero-heading">
                让想法，<br /><em>乘风而行。</em>
              </h3>
              <h3 v-else-if="design.id === 'river'" class="b-hero-heading">
                心有山海，<br />自有<span>知舟。</span>
              </h3>
              <h3 v-else class="b-hero-heading" lang="en">THINK<br /><span>BEYOND.</span></h3>
              <p class="b-hero-description">
                {{
                  design.id === 'paper'
                    ? '从一个问题开始，让散落的知识汇成方向。'
                    : design.id === 'river'
                      ? '让知识流动，让想法抵达。'
                      : '让思考，不止于此。'
                }}
              </p>
            </div>
            <div class="b-hero-seal" aria-hidden="true">
              {{ design.id === 'paper' ? '知行' : design.id === 'river' ? '山海' : '留白' }}
            </div>
            <div class="b-hero-caption" aria-hidden="true">
              {{ design.english }}<ArrowDownRight :size="22" />
            </div>
          </section>
          <div class="b-home-bottom">
            <div class="b-compose-wrap">
              <div class="b-compose-label">
                <BrandMark :variant="design.id" :size="20" /><span>把你的想法，交给知舟</span
                ><span class="b-compose-label-en">START SOMETHING</span>
              </div>
              <ChatComposer
                ref="composer"
                v-model="draft"
                :tooltip-portal-target="portalTarget"
                @send="submit"
              />
            </div>
            <div class="b-suggestions">
              <button
                v-for="(title, index) in suggestionTitles"
                :key="title"
                type="button"
                @click="fill(title)"
              >
                <span class="b-suggestion-number">0{{ index + 1 }}</span
                ><span>{{ title }}</span
                ><ArrowUpRight :size="16" />
              </button>
            </div>
            <div class="b-home-foot">
              <span>让工作，始于一句话。</span><span>静态演示 / 不连接 AI 服务</span>
            </div>
          </div>
        </div>
        <template v-else-if="activeConversation">
          <section ref="scrollArea" class="b-messages" aria-label="品牌原型消息">
            <div class="b-chat-intro">
              <span>THOUGHTS, TAKING SHAPE.</span><BrandMark :variant="design.id" :size="32" />
            </div>
            <article
              v-for="message in activeConversation.messages"
              :key="message.id"
              class="b-message"
              :class="`b-message--${message.role}`"
              :aria-label="message.role === 'user' ? '你的消息' : '知舟演示回复'"
            >
              <div v-if="message.role === 'assistant'" class="b-message-heading">
                <BrandMark :variant="design.id" :size="25" /><span>知舟</span
                ><small>演示回复</small>
              </div>
              <div class="b-message-body">
                <template v-for="(block, index) in message.blocks" :key="index"
                  ><p v-if="block.type === 'paragraph'">{{ block.text }}</p>
                  <ul v-else-if="block.type === 'list'">
                    <li v-for="(item, itemIndex) in block.items" :key="itemIndex">{{ item }}</li>
                  </ul>
                  <div v-else class="b-code">
                    <span>{{ block.language }}</span>
                    <pre><code>{{ block.text }}</code></pre>
                  </div></template
                >
              </div>
            </article>
          </section>
          <footer class="b-chat-footer">
            <div class="b-chat-footer-inner">
              <div class="b-conversation-note">
                <Compass :size="13" />沿着问题，继续探索<button type="button" @click="navigate()">
                  <CornerUpLeft :size="13" />开启新话题
                </button>
              </div>
              <ChatComposer
                ref="composer"
                v-model="draft"
                :tooltip-portal-target="portalTarget"
                @send="submit"
              />
              <p>固定演示内容，不由 AI 生成。仅在本页面内保留。</p>
            </div>
          </footer>
        </template>
      </main>
    </div>
  </div>
</template>

<style src="./brand-scene.css" scoped></style>
