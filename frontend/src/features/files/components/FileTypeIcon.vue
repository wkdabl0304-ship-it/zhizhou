<!-- 原创格式图标：明暗主题共用同一造型与专用色板，纸面填充不随页面背景变暗。 -->
<script setup lang="ts">
import { computed } from 'vue'
import { describeFile } from '../file-types'

const props = defineProps<{ name: string; kind: 'file' | 'folder' }>()
// 公开名称只用于显示分类，图标没有文件执行、解析或外部素材请求。
const appearance = computed(() => describeFile(props.name, props.kind))
</script>
<template>
  <span
    class="file-type-icon"
    :data-kind="appearance.category"
    role="img"
    :aria-label="appearance.label"
    :title="appearance.label"
  >
    <svg v-if="appearance.category === 'folder'" viewBox="0 0 40 44" fill="none" aria-hidden="true">
      <!-- 将原来的透明叠色预先与纸色混合，两个主题都能看到完整的文件夹实体。 -->
      <path
        d="M3 12a3 3 0 0 1 3-3h9l4 4h15a3 3 0 0 1 3 3v19H3Z"
        fill="color-mix(in srgb, currentColor 22%, var(--file-icon-paper))"
      />
      <path class="file-folder-paper" d="M5 16h29v17H5Z" fill="var(--file-icon-paper)" />
      <path
        d="M3 21a3 3 0 0 1 3-3h30l-3 17a3 3 0 0 1-3 2H6a3 3 0 0 1-3-3Z"
        fill="color-mix(in srgb, currentColor 74%, var(--file-icon-paper))"
      />
      <path
        d="M4 21h31M7 32h11"
        stroke="var(--file-icon-paper)"
        stroke-width="1.4"
        stroke-linecap="round"
        opacity=".7"
      />
    </svg>
    <svg v-else viewBox="0 0 40 44" fill="none" aria-hidden="true">
      <path
        class="file-icon-paper"
        d="M9 3h16l8 8v27a3 3 0 0 1-3 3H9a3 3 0 0 1-3-3V6a3 3 0 0 1 3-3Z"
        fill="var(--file-icon-paper)"
        stroke="currentColor"
        stroke-opacity=".5"
      />
      <path d="M25 3v8h8M9 3h16v8h8v19H6V6a3 3 0 0 1 3-3Z" fill="currentColor" fill-opacity=".12" />
      <g
        class="file-icon-glyph"
        stroke="currentColor"
        stroke-width="1.6"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <path
          v-if="appearance.category === 'pdf'"
          d="M14 25c3-4 5-8 5-11-3 0-1 8 7 10-2-3-11-2-12 1Z"
        />
        <path
          v-else-if="appearance.category === 'word'"
          d="m12 16 2 9 4-7 4 7 2-9M26 18h2m-2 4h2"
        />
        <path
          v-else-if="appearance.category === 'sheet'"
          d="M12 15h16v11H12Zm0 4h16m-16 3h16m-11-7v11m5-11v11"
        />
        <path
          v-else-if="appearance.category === 'slides'"
          d="M12 15h16v10H12Zm8 10v3m-4 0h8m-8-6v-3m4 3v-5m4 5v-2"
        />
        <g v-else-if="appearance.category === 'image'">
          <path d="M12 15h16v12H12Zm0 10 5-5 4 4 3-3 4 4" />
          <circle cx="24" cy="18" r="1" fill="currentColor" stroke="none" />
        </g>
        <path
          v-else-if="appearance.category === 'audio'"
          d="M18 24V15l9-2v9m-9-6 9-2m-9 10c0 3-6 4-6 1s6-4 6-1Zm9-2c0 3-6 4-6 1s6-4 6-1Z"
        />
        <path v-else-if="appearance.category === 'video'" d="M12 15h16v12H12Zm6 3 6 3-6 3Z" />
        <path
          v-else-if="appearance.category === 'archive'"
          d="M19 13h3m-5 3h3m-1 3h3m-5 3h3m-1 3h3m-4 0h5v4h-5Z"
        />
        <path
          v-else-if="appearance.category === 'code'"
          d="m16 16-4 5 4 5m8-10 4 5-4 5m-3-11-3 14"
        />
        <path v-else-if="appearance.category === 'text'" d="M12 16h16m-16 4h16m-16 4h12" />
        <path
          v-else-if="appearance.category === 'ebook'"
          d="M20 17c-3-2-6-2-9-1v11c3-1 6-1 9 1 3-2 6-2 9-1V16c-3-1-6-1-9 1Zm0 0v11"
        />
        <g v-else-if="appearance.category === 'database'">
          <ellipse cx="20" cy="16" rx="7" ry="3" />
          <path d="M13 16v9c0 4 14 4 14 0v-9m-14 5c0 4 14 4 14 0" />
        </g>
        <path
          v-else-if="appearance.category === 'application'"
          d="M12 15h16v12H12Zm0 4h16m-12-2h.1m3 0h.1m-3 6 2 2 5-4"
        />
        <path v-else d="M14 16h12m-12 4h9m-9 4h6" />
      </g>
      <rect
        class="file-icon-badge"
        x="3"
        y="30"
        width="34"
        height="12"
        rx="3"
        fill="currentColor"
      />
      <text
        class="file-icon-label"
        x="20"
        y="38.6"
        text-anchor="middle"
        font-size="7.4"
        font-weight="700"
        letter-spacing=".35"
        fill="var(--file-icon-paper)"
        font-family="var(--font-sans)"
      >
        {{ appearance.badge }}
      </text>
    </svg>
  </span>
</template>
<style scoped>
.file-type-icon {
  display: inline-flex;
  width: 38px;
  height: 44px;
  flex-shrink: 0;
  color: var(--file-icon-neutral);
}
.file-type-icon svg {
  width: 100%;
  height: 100%;
}
.file-type-icon[data-kind='folder'] {
  color: var(--file-icon-gold);
}
.file-type-icon[data-kind='pdf'] {
  color: var(--file-icon-red);
}
.file-type-icon[data-kind='word'],
.file-type-icon[data-kind='video'] {
  color: var(--file-icon-blue);
}
.file-type-icon[data-kind='sheet'] {
  color: var(--file-icon-green);
}
.file-type-icon[data-kind='slides'],
.file-type-icon[data-kind='archive'],
.file-type-icon[data-kind='ebook'] {
  color: var(--file-icon-warm);
}
.file-type-icon[data-kind='image'],
.file-type-icon[data-kind='code'] {
  color: var(--file-icon-violet);
}
.file-type-icon[data-kind='audio'],
.file-type-icon[data-kind='database'] {
  color: var(--file-icon-teal);
}
@media (max-width: 760px) {
  .file-type-icon {
    width: 31px;
    height: 38px;
  }
}
</style>
