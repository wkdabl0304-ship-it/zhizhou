/** 聊天选择恢复协调：仅恢复活动上下文的失效选择，生成与编辑期间延后，不自动重发消息。 */
import { watch } from 'vue'
import { validateSelection, decodeSelection } from '@/features/model-selection/contract'
import type { ModelOptions, ModelSelection } from '@/features/model-selection/types'
import type { Conversation } from './types'

/** 为未持久化的选择寻找替代；已有会话的相同规则由后端在版本锁内裁决。 */
export function replacementSelection(
  options: ModelOptions,
  current: ModelSelection,
): ModelSelection | null {
  const models = options.providers.flatMap((provider) => provider.models)
  const same = models.find(
    (model) => model.model_configuration_id === current.model_configuration_id,
  )
  if (same)
    return decodeSelection({
      model_configuration_id: same.model_configuration_id,
      reasoning: same.reasoning_control.default,
    })
  if (options.default_selection) return decodeSelection(options.default_selection)
  const first = models[0]
  return first
    ? decodeSelection({
        model_configuration_id: first.model_configuration_id,
        reasoning: first.reasoning_control.default,
      })
    : null
}

/** 监听有效性与生命周期，外部同步触发一次恢复，失败不自行循环请求。 */
export function useModelRecovery(
  state: () => {
    row: Conversation | undefined
    selection: ModelSelection | null
    options: ModelOptions | null
    loading: boolean
    error: string
    editing: boolean
  },
  recover: () => Promise<void>,
): void {
  // 记录请求所针对的快照：保存结束后重新检查新版本，但同一失败快照不无限重试。
  let attempted: {
    row: Conversation | undefined
    options: ModelOptions
    selection: ModelSelection
    version: number | undefined
    issue: Conversation['modelSelectionIssue']
  } | null = null
  watch(
    () => {
      const value = state(),
        row = value.row
      return [
        value.options,
        value.selection,
        row,
        row?.modelSelectionIssue,
        row?.modelSelectionVersion,
        row?.running,
        row?.remoteRunning,
        row?.loading,
        row?.selectionSaving,
        value.loading,
        value.error,
        value.editing,
      ]
    },
    () => {
      const value = state(),
        row = value.row
      if (attempted?.row !== row || row?.running || row?.remoteRunning) attempted = null
      if (
        !value.options ||
        value.loading ||
        value.error ||
        value.editing ||
        !value.selection ||
        row?.running ||
        row?.remoteRunning ||
        row?.loading ||
        row?.deleting ||
        row?.unavailable ||
        row?.selectionSaving ||
        row?.loaded === false
      )
        return
      const models = value.options.providers.flatMap((provider) => provider.models)
      const invalid =
        row?.modelSelectionIssue ||
        validateSelection(
          value.selection,
          models.find(
            (model) => model.model_configuration_id === value.selection!.model_configuration_id,
          ),
        )
      if (!invalid || !models.length) return
      if (
        attempted &&
        attempted.row === row &&
        attempted.options === value.options &&
        attempted.selection === value.selection &&
        attempted.version === row?.modelSelectionVersion &&
        attempted.issue === row?.modelSelectionIssue
      )
        return
      attempted = {
        row,
        options: value.options,
        selection: value.selection,
        version: row?.modelSelectionVersion,
        issue: row?.modelSelectionIssue,
      }
      void recover()
    },
    { immediate: true, flush: 'post' },
  )
}
