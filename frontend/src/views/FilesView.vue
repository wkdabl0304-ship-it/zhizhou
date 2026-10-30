<!-- 资料库页面：编排空间、路由目录与操作弹窗，读取和传输逻辑分别保留在 files 模块。 -->
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowLeft,
  Building2,
  ChevronRight,
  FolderOpen,
  FolderPlus,
  Globe2,
  LockKeyhole,
  Settings2,
} from '@lucide/vue'
import { useAuthStore } from '@/features/auth/store'
import UiPageHeader from '@/shared/components/ui/UiPageHeader.vue'
import UiButton from '@/shared/components/ui/UiButton.vue'
import UiFeedback from '@/shared/components/ui/UiFeedback.vue'
import UiTag from '@/shared/components/ui/UiTag.vue'
import FileTable from '@/features/files/components/FileTable.vue'
import FileUpload from '@/features/files/components/FileUpload.vue'
import FileActionDialog from '@/features/files/components/FileActionDialog.vue'
import UploadLimitDialog from '@/features/files/components/UploadLimitDialog.vue'
import { useFileDirectory } from '@/features/files/useFileDirectory'
import { useFileUpload } from '@/features/files/useFileUpload'
import { downloadFile } from '@/features/files/api'
import { fileError, formatSize, SPACE_LABELS } from '@/features/files/format'
import type { FileAction, FileEntry, FileSpace } from '@/features/files/types'
import '@/features/files/files.css'

const route = useRoute(),
  router = useRouter(),
  auth = useAuthStore()
const spaceId = computed(() => (typeof route.query.space === 'string' ? route.query.space : ''))
const parentId = computed(() =>
  typeof route.query.folder === 'string' && route.query.folder ? route.query.folder : null,
)
const directory = useFileDirectory(() => ({ spaceId: spaceId.value, parentId: parentId.value }))
const {
  spaces,
  spaceCursor,
  spacesLoading,
  spacesError,
  space,
  entries,
  breadcrumbs,
  cursor,
  loading,
  error,
} = directory
const action = ref<FileAction | null>(null),
  policySpace = ref<FileSpace | null>(null)
const downloadError = ref(''),
  downloading = ref<string[]>([])
const downloads = new Map<string, AbortController>()
const policyAllowed = computed(
  () =>
    !!space.value && auth.can('file_upload_limit:update', space.value.department_id ?? undefined),
)
const currentName = computed(
  () => breadcrumbs.value.at(-1)?.name ?? space.value?.name ?? '资料目录',
)
const locationKey = computed(() => `${spaceId.value}/${parentId.value ?? ''}`)
const transfer = useFileUpload(
  () => ({ space: space.value, parentId: parentId.value, key: locationKey.value }),
  () => {
    void directory.reload()
  },
)
const { busy: uploading, current: uploadProgress, failures: uploadFailures } = transfer
const dragging = ref(false),
  dropFolderId = ref<string | null>(null),
  dropError = ref('')
const dropName = computed(
  () => entries.value.find((entry) => entry.id === dropFolderId.value)?.name ?? currentName.value,
)
// 新一批传输开始后清除旧投递错误，避免已修正的操作仍残留之前的失败说明。
watch(uploading, (value) => {
  if (value) dropError.value = ''
})

/** 清除拖放指示，避免离开列表或切换位置后保留过期的接收高亮。 */
function clearDrop(): void {
  dragging.value = false
  dropFolderId.value = null
}

/** 根据光标下的目录行确认接收位置，文件行和列表空白均落到当前目录。 */
function folderAt(event: DragEvent): FileEntry | undefined {
  const row =
    event.target instanceof Element ? event.target.closest<HTMLElement>('[data-folder-id]') : null
  return entries.value.find(
    (entry) => entry.kind === 'folder' && entry.id === row?.dataset.folderId,
  )
}

/** 接受外部文件拖入目录，只有当前可上传且无传输时显示复制光标和目标高亮。 */
function dragOver(event: DragEvent): void {
  if (!event.dataTransfer?.types.includes('Files')) return
  event.preventDefault()
  if (!space.value?.capabilities.includes('upload') || uploading.value) {
    event.dataTransfer.dropEffect = 'none'
    clearDrop()
    return
  }
  event.dataTransfer.dropEffect = 'copy'
  dragging.value = true
  dropFolderId.value = folderAt(event)?.id ?? null
}

/** 离开整个目录表面时取消指示，子节点间移动不闪烁或清空目标。 */
function dragLeave(event: DragEvent): void {
  if (
    !(event.relatedTarget instanceof Node) ||
    !(event.currentTarget as HTMLElement).contains(event.relatedTarget)
  )
    clearDrop()
}

/** 将外部文件交给实际接收目录；落到文件夹后先进入该目录，再上传到冻结目标。 */
async function drop(event: DragEvent): Promise<void> {
  event.preventDefault()
  const folder = folderAt(event)
  clearDrop()
  if (!event.dataTransfer?.types.includes('Files')) return
  dropError.value = ''
  if (!space.value) {
    dropError.value = loading.value
      ? '目录正在读取，请稍候再拖入文件。'
      : '当前目录不可用，请重新选择空间。'
    return
  }
  if (!space.value.capabilities.includes('upload')) {
    dropError.value = '当前空间没有上传权限。'
    return
  }
  if (uploading.value) {
    dropError.value = '请等待当前操作完成后再拖入文件。'
    return
  }
  // 整文件夹上传需要递归目录协议；明确拒绝，避免把本地目录误当成零字节原件。
  if (Array.from(event.dataTransfer.items).some((item) => item.webkitGetAsEntry?.()?.isDirectory)) {
    dropError.value = '暂不支持上传整个文件夹，请打开本地文件夹并选择其中的文件。'
    return
  }
  const files = Array.from(event.dataTransfer.files)
  if (!files.length) return
  const destination = { space: { ...space.value }, parentId: folder?.id ?? parentId.value }
  const token = auth.accessToken
  if (folder) {
    const failure = await router.push({
      name: 'files',
      query: { space: spaceId.value, folder: folder.id },
    })
    if (failure) return
    await nextTick()
  }
  if (
    auth.accessToken === token &&
    route.name === 'files' &&
    spaceId.value === destination.space.id
  )
    await transfer.upload(files, destination)
}

/** 将空间和父目录写入 URL，浏览器历史与分享链接可恢复同一位置。 */
function navigate(id: string, folder: string | null = null): void {
  void router.push({ name: 'files', query: { space: id, ...(folder ? { folder } : {}) } })
}

/** 回到父目录；根目录不提供虚假的返回操作。 */
function up(): void {
  navigate(spaceId.value, breadcrumbs.value.at(-2)?.id ?? null)
}

/** 冻结当前空间、父节点或条目版本，避免刷新后表单目标漂移。 */
function openAction(kind: FileAction['kind'], entry?: FileEntry): void {
  if (!space.value) return
  if (kind === 'create')
    action.value = { kind, space: { ...space.value }, parentId: parentId.value }
  else if (entry) action.value = { kind, space: { ...space.value }, entry: { ...entry } }
}

/** 关闭已完成操作，通过目录重读展示结果，不添加成功反馈。 */
function saved(): void {
  action.value = null
  policySpace.value = null
  void directory.reload()
}

/** 下载指定原件，防止重复点击，并将异常集中展示一次。 */
async function download(entry: FileEntry): Promise<void> {
  if (downloads.has(entry.id)) return
  downloadError.value = ''
  const controller = new AbortController()
  downloads.set(entry.id, controller)
  downloading.value = [...downloads.keys()]
  try {
    await downloadFile(entry, controller.signal)
  } catch (failure) {
    if (!controller.signal.aborted) downloadError.value = fileError(failure)
  } finally {
    downloads.delete(entry.id)
    downloading.value = [...downloads.keys()]
  }
}

/** 工作区重新激活时同步目录，但不打断正在编辑的冻结版本表单。 */
function synchronize(): void {
  if (
    document.hidden ||
    action.value ||
    policySpace.value ||
    loading.value ||
    dragging.value ||
    uploading.value
  )
    return
  // 已加载目录的后台同步不锁定投递；真正的上传和新目录初始化由各自状态约束。
  void directory.loadSpaces()
  void directory.reload()
}

// 首次进入优先打开个人空间；后端列表可分页，显式空间链接不依赖其已出现在第一页。
watch(spaces, (items) => {
  if (!spaceId.value && items.length) {
    const initial = items.find((item) => item.kind === 'personal') ?? items[0]!
    void router.replace({ name: 'files', query: { space: initial.id } })
  }
})
watch(locationKey, () => {
  action.value = null
  policySpace.value = null
  downloadError.value = ''
  dropError.value = ''
  clearDrop()
})
// 授权或部门变化时关闭旧表单；目录层同时重新确认当前空间可见性和能力。
watch(
  () => JSON.stringify([auth.accessToken, auth.user?.department, auth.user?.grants]),
  () => {
    action.value = null
    policySpace.value = null
    transfer.reset()
    clearDrop()
  },
)
onMounted(() => {
  void directory.loadSpaces()
  window.addEventListener('focus', synchronize)
  document.addEventListener('visibilitychange', synchronize)
})
onBeforeUnmount(() => {
  window.removeEventListener('focus', synchronize)
  document.removeEventListener('visibilitychange', synchronize)
  for (const controller of downloads.values()) controller.abort()
})
</script>
<template>
  <div class="files-page">
    <UiPageHeader class="files-header" title="资料库" size="sm" />
    <div class="files-scroll">
      <div class="files-workbench">
        <aside class="file-spaces" aria-label="资料空间">
          <div class="file-section-label"><span>资料空间</span></div>
          <nav aria-label="选择资料空间">
            <button
              v-for="item in spaces"
              :key="item.id"
              type="button"
              class="file-space-button"
              :class="{ 'is-active': item.id === spaceId }"
              :aria-current="item.id === spaceId ? 'location' : undefined"
              @click="navigate(item.id)"
            >
              <component
                :is="
                  item.kind === 'personal'
                    ? LockKeyhole
                    : item.kind === 'department'
                      ? Building2
                      : Globe2
                "
                :size="18"
              />
              <span
                ><strong>{{ item.name }}</strong
                ><small>{{
                  item.kind === 'personal' ? '仅自己可见' : SPACE_LABELS[item.kind]
                }}</small></span
              ><ChevronRight :size="14" />
            </button>
          </nav>
          <p v-if="spacesLoading" class="file-hint" role="status">正在读取空间…</p>
          <UiFeedback
            v-if="spacesError"
            :message="spacesError"
            retry-label="重试空间列表"
            :busy="spacesLoading"
            @retry="directory.loadSpaces()"
          />
          <UiButton
            v-if="spaceCursor"
            size="sm"
            variant="ghost"
            :loading="spacesLoading"
            @click="directory.loadSpaces(true)"
            >更多空间</UiButton
          >
        </aside>
        <section class="file-directory" aria-label="文件目录" :aria-busy="loading">
          <nav v-if="space" class="file-address-bar" aria-label="目录路径">
            <UiButton
              size="sm"
              variant="ghost"
              aria-label="上一级"
              :disabled="!parentId"
              @click="up"
              ><ArrowLeft :size="16"
            /></UiButton>
            <div class="file-breadcrumbs">
              <FolderOpen :size="16" aria-hidden="true" />
              <button
                type="button"
                :aria-current="!parentId ? 'location' : undefined"
                @click="navigate(space.id)"
              >
                {{ space.name }}
              </button>
              <template v-for="(crumb, index) in breadcrumbs" :key="crumb.id"
                ><ChevronRight :size="13" aria-hidden="true" />
                <button
                  type="button"
                  :aria-current="index === breadcrumbs.length - 1 ? 'location' : undefined"
                  @click="navigate(space.id, crumb.id)"
                >
                  {{ crumb.name }}
                </button>
              </template>
            </div>
          </nav>
          <div class="file-directory-heading">
            <h2>{{ currentName }}</h2>
            <span v-if="space">{{ SPACE_LABELS[space.kind] }}</span>
          </div>
          <div v-if="space" class="file-directory-actions file-toolbar" aria-label="文件操作">
            <FileUpload
              v-if="space.capabilities.includes('upload')"
              :busy="uploading"
              :disabled="loading"
              @files="transfer.upload($event)"
              @cancel="transfer.cancel"
            />
            <UiButton
              v-if="space.capabilities.includes('upload')"
              size="sm"
              :disabled="loading"
              @click="openAction('create')"
              ><FolderPlus :size="16" />新建文件夹</UiButton
            >
            <UiButton
              v-if="policyAllowed"
              size="sm"
              variant="ghost"
              :disabled="loading"
              @click="policySpace = { ...space }"
              ><Settings2 :size="15" />上传上限</UiButton
            >
            <span v-if="!space.capabilities.includes('upload')" class="file-readonly"
              ><LockKeyhole :size="14" />当前空间可浏览与下载</span
            >
          </div>
          <p v-if="uploading" class="file-transfer-status" role="status">
            正在上传 · {{ uploadProgress }}
          </p>
          <UiFeedback v-if="uploadFailures.length" class="upload-failures"
            ><ul>
              <li v-for="(failure, index) in uploadFailures" :key="index">{{ failure }}</li>
            </ul></UiFeedback
          >
          <div
            class="file-list-surface"
            :class="{ 'is-dragging': dragging && !dropFolderId }"
            role="region"
            aria-label="目录内容区"
            @dragenter="dragOver"
            @dragover="dragOver"
            @dragleave="dragLeave"
            @drop="drop"
          >
            <p v-if="dragging" class="file-drop-status" role="status">
              松开以上传到「{{ dropName }}」
            </p>
            <UiFeedback v-if="dropError" :message="dropError" />
            <UiFeedback
              v-if="error"
              :message="error"
              retry-label="重新读取目录"
              :busy="loading"
              @retry="directory.reload()"
            />
            <UiFeedback v-if="downloadError" :message="downloadError" />
            <p v-if="loading" class="file-loading" role="status">正在整理目录…</p>
            <FileTable
              v-if="space && entries.length"
              :entries="entries"
              :space="space"
              :downloading="downloading"
              :drop-folder-id="dropFolderId"
              @folder="navigate(spaceId, $event.id)"
              @download="download"
              @rename="openAction('rename', $event)"
              @delete="openAction('delete', $event)"
            />
            <div v-else-if="!loading && !error && space" class="file-empty">
              <FolderOpen :size="40" :stroke-width="1" />
              <h3>暂无文件</h3>
              <p v-if="space.capabilities.includes('upload')">上传文件或拖入此目录</p>
            </div>
            <p
              v-if="!spaceId && !spacesLoading && !spacesError && !spaces.length"
              class="file-hint"
            >
              当前没有可用的资料空间。
            </p>
            <UiButton
              v-if="cursor"
              class="file-more"
              :loading="loading"
              @click="directory.reload(true)"
              >加载更多资料</UiButton
            >
          </div>
          <footer v-if="space" class="file-footnote">
            <span
              ><UiTag size="xs">{{ entries.length }}{{ cursor ? '+' : '' }}</UiTag> 个项目</span
            ><span>单文件上限 {{ formatSize(space.max_file_size_bytes) }}</span>
          </footer>
        </section>
      </div>
    </div>
    <FileActionDialog
      v-if="action"
      :action="action"
      @close="action = null"
      @saved="saved"
      @conflict="directory.reload()"
    />
    <UploadLimitDialog
      v-if="policySpace"
      :space="policySpace"
      @close="policySpace = null"
      @saved="saved"
      @conflict="directory.reload()"
    />
  </div>
</template>
