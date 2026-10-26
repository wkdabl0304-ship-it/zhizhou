<!-- 管理端推理范围：固定策略不开放聊天编辑；自选策略仅从当前目录选择方式、档位和预算。 -->
<script setup lang="ts">
import { computed } from 'vue'
import type { CatalogModel, Reasoning } from '../types'
import type {
  ConcreteReasoning,
  ReasoningPolicy,
  SelectablePolicy,
} from '@/features/model-selection/types'
import { modeLabels, effortLabels } from '../validation'
const props = defineProps<{ model: CatalogModel; reasoning: Reasoning; maxOutput: number }>()
const policy = defineModel<ReasoningPolicy>({ required: true })
const modes = computed(() =>
  props.model.reasoning.allowed_modes.filter(
    (mode): mode is ConcreteReasoning['mode'] => mode !== 'default',
  ),
)
/** 从固定切换到自选时，以当前默认分支建立合法初始范围。 */
function changePolicy(event: Event): void {
  if ((event.target as HTMLSelectElement).value === 'fixed') {
    policy.value = { mode: 'fixed' }
    return
  }
  const value = props.reasoning.mode === 'default' ? props.model.reasoning.default : props.reasoning
  const mode = value.mode === 'default' ? modes.value[0]! : value.mode
  policy.value = ranges([mode])
}
/** 组装完整替换策略，移除不适用的档位或预算字段。 */
function ranges(allowed: ConcreteReasoning['mode'][]): SelectablePolicy {
  const previous = policy.value.mode === 'selectable' ? policy.value : undefined
  const range = props.model.reasoning.budget
  return {
    mode: 'selectable',
    allowed_modes: [...allowed],
    effort_options: allowed.includes('effort')
      ? previous?.effort_options.length
        ? [...previous.effort_options]
        : [...props.model.reasoning.effort_options]
      : [],
    budget:
      allowed.includes('budget') && range
        ? previous?.budget
          ? { ...previous.budget }
          : {
              min: range.min,
              max: Math.min(
                range.max,
                props.model.reasoning.budget_must_fit_output ? props.maxOutput - 1 : range.max,
              ),
            }
        : null,
  }
}
/** 按目录顺序添加或移除允许方式，不允许不相关参数残留在请求中。 */
function toggleMode(mode: ConcreteReasoning['mode'], event: Event): void {
  if (policy.value.mode !== 'selectable') return
  const selected = new Set(policy.value.allowed_modes)
  if ((event.target as HTMLInputElement).checked) selected.add(mode)
  else selected.delete(mode)
  policy.value = ranges(modes.value.filter((mode) => selected.has(mode)))
}
/** 修改开放档位，保留后端目录给出的原始顺序。 */
function toggleEffort(effort: string, event: Event): void {
  if (policy.value.mode !== 'selectable') return
  const selected = new Set(policy.value.effort_options)
  if ((event.target as HTMLInputElement).checked) selected.add(effort)
  else selected.delete(effort)
  policy.value = {
    ...policy.value,
    effort_options: props.model.reasoning.effort_options.filter((value) => selected.has(value)),
  }
}
/** 保留输入中的无效预算供父表单提示，避免输入未完成时写请求或静默裁剪。 */
function budget(key: 'min' | 'max', event: Event): void {
  if (policy.value.mode === 'selectable' && policy.value.budget)
    policy.value = {
      ...policy.value,
      budget: { ...policy.value.budget, [key]: (event.target as HTMLInputElement).valueAsNumber },
    }
}
</script>
<template>
  <label
    >聊天推理策略<select name="reasoning_policy" :value="policy.mode" @change="changePolicy">
      <option value="fixed">固定推理设置</option>
      <option value="selectable">允许用户在范围内自选</option></select
    ><small>固定时聊天使用上方默认值；自选时默认值必须在允许范围内。</small></label
  >
  <div
    v-if="policy.mode === 'selectable'"
    class="config-policy"
    role="group"
    aria-label="允许的推理范围"
  >
    <p class="config-hint">允许的推理方式</p>
    <label v-for="mode in modes" :key="mode" class="config-switch"
      ><input
        type="checkbox"
        :name="`allow_${mode}`"
        :checked="policy.allowed_modes.includes(mode)"
        @change="toggleMode(mode, $event)"
      />{{ modeLabels[mode] }}</label
    >
    <template v-if="policy.allowed_modes.includes('effort')"
      ><p class="config-hint">允许的档位</p>
      <label v-for="effort in model.reasoning.effort_options" :key="effort" class="config-switch"
        ><input
          type="checkbox"
          :name="`allow_effort_${effort}`"
          :checked="policy.effort_options.includes(effort)"
          @change="toggleEffort(effort, $event)"
        />{{ effortLabels[effort] ?? effort }} · {{ effort }}</label
      ></template
    >
    <template v-if="policy.budget"
      ><label
        >允许预算下限<input
          name="policy_budget_min"
          type="number"
          :value="policy.budget.min"
          @input="budget('min', $event)" /></label
      ><label
        >允许预算上限<input
          name="policy_budget_max"
          type="number"
          :value="policy.budget.max"
          @input="budget('max', $event)" /></label
    ></template>
  </div>
</template>
