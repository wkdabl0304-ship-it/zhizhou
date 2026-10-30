<!-- 模型强度白名单：将不思考、原生档位和预算统一成一组可选项，不提供重复的模式或策略开关。 -->
<script setup lang="ts">
import UiCheckbox from '@/shared/components/ui/UiCheckbox.vue'
import UiInput from '@/shared/components/ui/UiInput.vue'
import { computed } from 'vue'
import { effortLabels } from '../validation'
import type { CatalogModel } from '../types'
import type { SelectablePolicy } from '@/features/model-selection/types'
const props = defineProps<{ model: CatalogModel; maxOutput: number }>()
const policy = defineModel<SelectablePolicy>({ required: true })
const budgetMaximum = computed(() =>
  props.model.reasoning.budget
    ? Math.min(
        props.model.reasoning.budget.max,
        props.model.reasoning.budget_must_fit_output
          ? props.maxOutput - 1
          : props.model.reasoning.budget.max,
      )
    : 0,
)

/** 更新单个允许强度，同时保持联合类型中方式、档位和预算字段一致。 */
function toggle(value: string, enabled: boolean): void {
  const current = policy.value
  const efforts = new Set(current.effort_options)
  if (value !== 'off' && value !== 'budget') {
    if (enabled) efforts.add(value)
    else efforts.delete(value)
  }
  const modes = new Set(current.allowed_modes)
  if (value === 'off' || value === 'budget') {
    if (enabled) modes.add(value)
    else modes.delete(value)
  }
  if (efforts.size) modes.add('effort')
  else modes.delete('effort')
  const range = props.model.reasoning.budget
  policy.value = {
    mode: 'selectable',
    allowed_modes: props.model.reasoning.allowed_modes.filter(
      (mode): mode is SelectablePolicy['allowed_modes'][number] =>
        mode !== 'default' && modes.has(mode),
    ),
    effort_options: props.model.reasoning.effort_options.filter((effort) => efforts.has(effort)),
    budget:
      modes.has('budget') && range
        ? (current.budget ?? { min: range.min, max: Math.max(range.min, budgetMaximum.value) })
        : null,
  }
}

/** 更新预算端点，保留无效输入以便保存时解释错误，不静默扩大允许范围。 */
function updateBudget(key: 'min' | 'max', value: string | number | undefined): void {
  if (!policy.value.budget) return
  policy.value = { ...policy.value, budget: { ...policy.value.budget, [key]: Number(value) } }
}
</script>
<template>
  <div class="model-strength-options" role="group" aria-label="允许的推理强度">
    <UiCheckbox
      v-if="model.reasoning.allowed_modes.includes('off')"
      name="allow_off"
      :model-value="policy.allowed_modes.includes('off')"
      @update:model-value="toggle('off', $event)"
      >不思考</UiCheckbox
    >
    <UiCheckbox
      v-for="effort in model.reasoning.effort_options"
      :key="effort"
      :name="`allow_effort_${effort}`"
      :model-value="policy.effort_options.includes(effort)"
      @update:model-value="toggle(effort, $event)"
      >{{ effortLabels[effort] ?? effort
      }}<span class="model-strength-native">{{ effort }}</span></UiCheckbox
    >
    <UiCheckbox
      v-if="model.reasoning.budget"
      name="allow_budget"
      :model-value="policy.allowed_modes.includes('budget')"
      @update:model-value="toggle('budget', $event)"
      >按预算思考</UiCheckbox
    >
  </div>
  <div v-if="policy.budget" class="model-strength-budget" role="group" aria-label="允许的思考预算">
    <label
      >最低预算<UiInput
        name="policy_budget_min"
        type="number"
        :model-value="policy.budget.min"
        :min="model.reasoning.budget!.min"
        :max="budgetMaximum"
        step="1"
        @update:model-value="updateBudget('min', $event)"
    /></label>
    <label
      >最高预算<UiInput
        name="policy_budget_max"
        type="number"
        :model-value="policy.budget.max"
        :min="model.reasoning.budget!.min"
        :max="budgetMaximum"
        step="1"
        @update:model-value="updateBudget('max', $event)"
    /></label>
    <small
      >单位 tokens，范围 {{ model.reasoning.budget!.min.toLocaleString() }}–{{
        budgetMaximum.toLocaleString()
      }}{{ model.reasoning.budget_must_fit_output ? '，须小于输出上限' : '' }}。</small
    >
  </div>
</template>
<style>
.model-strength-options {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 16px;
}
.config-fields .model-strength-options .ui-checkbox {
  margin: 0;
  padding: 9px 12px;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--surface);
  transition:
    border-color var(--duration-fast),
    background var(--duration-fast);
}
.model-strength-options .ui-checkbox:has(input:checked) {
  border-color: var(--brand);
  background: var(--brand-soft);
}
.model-strength-options .ui-checkbox:hover {
  border-color: var(--brand);
}
.model-strength-options .ui-checkbox:has(input:focus-visible) {
  outline: 2px solid var(--brand);
  outline-offset: 3px;
}
.model-strength-native {
  margin-left: 6px;
  color: var(--text-muted);
  font: 10px var(--font-mono);
}
.model-strength-budget {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 16px;
  margin-top: 18px;
}
.config-fields .model-editor .model-strength-budget label {
  margin: 0;
}
.model-strength-budget > small {
  grid-column: 1 / -1;
  line-height: 1.7;
}
@media (prefers-reduced-motion: reduce) {
  .config-fields .model-strength-options .ui-checkbox {
    transition: none;
  }
}
</style>
