/** 文件上传状态：统一按钮与目录拖放的传输生命周期，冻结目标并隔离离页后的响应。 */
import { onScopeDispose, ref, watch } from 'vue'
import { uploadFile } from './api'
import { fileError, formatSize } from './format'
import type { FileSpace } from './types'

/** 一批文件的固定接收位置，不随浏览中的目录或分页响应改变。 */
export interface UploadDestination {
  space: FileSpace
  parentId: string | null
}

/** 为资料页管理顺序上传、手动中止和失败说明；切换位置时释放旧队列。 */
export function useFileUpload(
  location: () => { space: FileSpace | null; parentId: string | null; key: string },
  uploaded: () => void,
) {
  const busy = ref(false),
    current = ref(''),
    failures = ref<string[]>([])
  let controller: AbortController | undefined

  /** 清理旧位置的传输与反馈，迟到请求不得更新新目录或新批次。 */
  function reset(): void {
    const previous = controller
    controller = undefined
    previous?.abort()
    busy.value = false
    current.value = ''
    failures.value = []
  }

  /** 将文件逐一上传到固定位置，允许空文件；失败不自动重试，结束后重新核对目录。 */
  async function upload(files: File[], destination?: UploadDestination): Promise<void> {
    const target = destination ?? location()
    if (busy.value || !files.length || !target.space?.capabilities.includes('upload')) return
    const { space, parentId } = target
    const request = (controller = new AbortController())
    busy.value = true
    failures.value = []
    try {
      for (const [index, file] of files.entries()) {
        if (request.signal.aborted) break
        current.value = `${index + 1} / ${files.length} · ${file.name}`
        if (file.size > space.max_file_size_bytes) {
          failures.value.push(
            `${file.name}：超过当前单文件上限 ${formatSize(space.max_file_size_bytes)}。`,
          )
          continue
        }
        try {
          await uploadFile(space.id, parentId, file, request.signal)
        } catch (failure) {
          if (request.signal.aborted) break
          failures.value.push(
            `${file.name}：${fileError(failure)} 请先查看目录，再决定是否重新选择上传。`,
          )
        }
      }
    } finally {
      if (controller === request) {
        busy.value = false
        current.value = ''
        // 中止不能保证服务端未发布；完成、失败和主动中止都重新读取当前目标。
        uploaded()
      }
    }
  }

  /** 中止当前文件及后续队列，保留需要核对目录的单条说明。 */
  function cancel(): void {
    if (!controller || controller.signal.aborted) return
    controller.abort()
    failures.value.push('上传已中止；服务端可能已接收当前文件，请查看目录后再决定是否重新上传。')
  }

  // 同空间不同目录也需要取消；能力撤销时清空旧状态，服务端继续独立复查每次写入。
  watch(() => location().key, reset)
  watch(
    () => location().space,
    (space) => {
      if (space && !space.capabilities.includes('upload')) reset()
    },
  )
  onScopeDispose(reset)
  return { busy, current, failures, upload, cancel, reset }
}
