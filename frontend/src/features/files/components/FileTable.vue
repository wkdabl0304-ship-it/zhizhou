<!-- 资料列表：以文件名为阅读主轴，目录单击进入，行内操作始终支持键盘及触屏。 -->
<script setup lang="ts">
import { Download, Pencil, Trash2 } from '@lucide/vue'
import UiIconButton from '@/shared/components/ui/UiIconButton.vue'
import { formatDate, formatSize } from '../format'
import type { FileEntry, FileSpace } from '../types'
import FileTypeIcon from './FileTypeIcon.vue'
import { describeFile } from '../file-types'

defineProps<{
  entries: FileEntry[]
  space: FileSpace
  downloading: string[]
  dropFolderId?: string | null
}>()
const emit = defineEmits<{
  folder: [entry: FileEntry]
  download: [entry: FileEntry]
  rename: [entry: FileEntry]
  delete: [entry: FileEntry]
}>()

/** 单击文件夹行的非操作区域即可进入，名称按钮保留原生键盘语义且不重复触发。 */
function openFolder(entry: FileEntry, event: MouseEvent): void {
  if (entry.kind !== 'folder') return
  if (
    event.target instanceof Element &&
    event.target.closest('button, a, input, .file-actions-column')
  )
    return
  emit('folder', entry)
}
</script>
<template>
  <table class="file-table">
    <caption class="sr-only">
      当前目录的文件与文件夹
    </caption>
    <thead>
      <tr>
        <th scope="col">名称</th>
        <th scope="col" class="file-size-column">大小</th>
        <th scope="col" class="file-date-column">最近修改</th>
        <th scope="col" class="file-actions-column">操作</th>
      </tr>
    </thead>
    <tbody>
      <tr
        v-for="entry in entries"
        :key="entry.id"
        :data-folder-id="entry.kind === 'folder' ? entry.id : undefined"
        :class="{
          'is-drop-target': entry.id === dropFolderId,
          'is-folder-row': entry.kind === 'folder',
        }"
        @click="openFolder(entry, $event)"
      >
        <td>
          <div class="file-name-cell">
            <FileTypeIcon :name="entry.name" :kind="entry.kind" />
            <div class="file-name-copy">
              <button
                v-if="entry.kind === 'folder'"
                type="button"
                class="file-folder-link"
                :title="entry.name"
                @click="$emit('folder', entry)"
              >
                {{ entry.name }}
              </button>
              <span v-else class="file-display-name" :title="entry.name">{{ entry.name }}</span>
              <small
                >{{
                  entry.kind === 'folder'
                    ? '文件夹'
                    : `${describeFile(entry.name).label} · ${formatSize(entry.size_bytes)}`
                }}<span class="file-mobile-date"> · {{ formatDate(entry.updated_at) }}</span></small
              >
            </div>
          </div>
        </td>
        <td class="file-size-column">{{ formatSize(entry.size_bytes) }}</td>
        <td class="file-date-column">
          <time
            :datetime="entry.updated_at"
            :title="new Date(entry.updated_at).toLocaleString('zh-CN')"
            >{{ formatDate(entry.updated_at) }}</time
          >
        </td>
        <td class="file-actions-column">
          <div class="file-row-actions">
            <UiIconButton
              v-if="entry.kind === 'file'"
              :label="`下载 ${entry.name}`"
              :disabled="downloading.includes(entry.id)"
              :aria-busy="downloading.includes(entry.id)"
              @click="$emit('download', entry)"
              ><Download :size="16"
            /></UiIconButton>
            <UiIconButton
              v-if="space.capabilities.includes('update')"
              :label="`重命名 ${entry.name}`"
              @click="$emit('rename', entry)"
              ><Pencil :size="15"
            /></UiIconButton>
            <UiIconButton
              v-if="space.capabilities.includes('delete')"
              :label="`删除 ${entry.name}`"
              class="file-delete"
              @click="$emit('delete', entry)"
              ><Trash2 :size="15"
            /></UiIconButton>
          </div>
        </td>
      </tr>
    </tbody>
  </table>
</template>
