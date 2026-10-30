<!-- 模型方案表单：按供应商及协议读取目录，集中编辑名称与输出上限，聊天思考由用户通过滑块自选。 -->
<script setup lang="ts">
import UiFeedback from '@/shared/components/ui/UiFeedback.vue'
import UiInput from '@/shared/components/ui/UiInput.vue'
import UiSelect from '@/shared/components/ui/UiSelect.vue'
import UiCheckbox from '@/shared/components/ui/UiCheckbox.vue'
import { computed, onBeforeUnmount, reactive, ref, toRaw, watch } from 'vue'
import { ApiError } from '@/features/auth/authenticated'
import UiButton from '@/shared/components/ui/UiButton.vue'
import ConfigEditor from './ConfigEditor.vue'
import ProviderLogo from '@/shared/components/ProviderLogo.vue'
import { Sparkles } from '@lucide/vue'
import ReasoningPolicyEditor from './ReasoningPolicyEditor.vue'
import type { SelectablePolicy } from '@/features/model-selection/types'
import { initialReasoning, defaultReasoningPolicy } from '../catalog-rows'
import { loadCatalog } from '../api'
import { explainConfigError, useModelConfigStore } from '../store'
import { validateModel } from '../validation'
import type { CatalogModel, ModelConfiguration, ModelInput, ProviderConfiguration } from '../types'
const props = defineProps<{
  provider: ProviderConfiguration
  previous?: ModelConfiguration
  /** 管理页只修改既有方案参数，模型归属和启停由卡片管理。 */
  managed?: boolean
  returnFocus?: HTMLElement | null
}>()
const emit = defineEmits<{
  close: []
  state: [value: { dirty: boolean; busy: boolean }]
}>()
const store = useModelConfigStore()
const previous = props.previous ? structuredClone(toRaw(props.previous)) : undefined
const draft = reactive<ModelInput>({
  name: previous?.name ?? '',
  provider_configuration_id: props.provider.id,
  catalog_model_id: previous?.catalog_model_id ?? '',
  reasoning: previous ? { ...previous.reasoning } : { mode: 'default' },
  max_output_tokens: previous?.max_output_tokens ?? 16384,
  enabled: previous?.enabled ?? true,
  reasoning_policy: previous ? structuredClone(previous.reasoning_policy) : { mode: 'fixed' },
})
let initial = JSON.stringify(draft)
const busy = ref(false),
  loading = ref(false),
  error = ref(''),
  catalogError = ref(''),
  conflict = ref(false)
const entries = ref<CatalogModel[]>([]),
  controller = new AbortController()
const spec = computed(() =>
  entries.value.find((item) => item.catalog_model_id === draft.catalog_model_id),
)
const dirty = computed(() => JSON.stringify(draft) !== initial)
// 选项文案来自当前目录；旧模型失效时以占位提示呈现，不伪造可选记录。
const catalogOptions = computed(() =>
  entries.value.map((item) => ({
    value: item.catalog_model_id,
    label: item.display_name + (item.available ? '' : ' · 不可用'),
    disabled: !item.available,
  })),
)
// 表单只管理允许范围，初始推理值在保存时自动落入该范围。
const policy = computed<SelectablePolicy>({
  get: () =>
    draft.reasoning_policy?.mode === 'selectable'
      ? draft.reasoning_policy
      : defaultReasoningPolicy(spec.value!, draft.max_output_tokens),
  set: (value) => {
    draft.reasoning_policy = value
  },
})
const thinkingHint = computed(() => {
  if (!spec.value) return ''
  if (!spec.value.reasoning.allowed_modes.includes('off'))
    return '此模型不支持关闭思考。用户可在勾选的强度之间拖动选择。'
  return '勾选用户可用的档位，至少保留一项。“不思考”对应聊天滑块的最左档。'
})
// 减小输出上限时只收紧预算上界；不自动增加或移除管理员勾选的强度。
watch(
  () => draft.max_output_tokens,
  (output) => {
    if (
      !spec.value?.reasoning.budget_must_fit_output ||
      !Number.isSafeInteger(output) ||
      !policy.value.budget
    )
      return
    const budget = policy.value.budget
    // 临时空值或不足最低预算的输入交给校验解释，不能顺带覆盖原先合法的预算范围。
    if (output <= budget.min) return
    if (budget.max >= output)
      draft.reasoning_policy = {
        ...policy.value,
        budget: { ...budget, max: Math.max(budget.min, output - 1) },
      }
  },
)
/** 读取匹配协议的目录，失败只影响当前编辑器，并提供显式重试。 */
async function load(): Promise<void> {
  loading.value = true
  catalogError.value = ''
  try {
    const data = await loadCatalog(
      props.provider.provider,
      props.provider.api_format,
      controller.signal,
    )
    if (controller.signal.aborted) return
    entries.value = data
    // 只规范化原始基线中的目录及策略，重试目录不能把用户已编辑的名称标记为已保存。
    const baseline = JSON.parse(initial) as ModelInput
    if (!previous && !draft.catalog_model_id) {
      draft.catalog_model_id = data.find((item) => item.available)?.catalog_model_id ?? ''
      changeModel()
      baseline.catalog_model_id = draft.catalog_model_id
      if (spec.value)
        baseline.max_output_tokens = Math.min(
          baseline.max_output_tokens,
          spec.value.max_output_tokens,
        )
    }
    if (spec.value && draft.reasoning_policy?.mode !== 'selectable') {
      draft.reasoning_policy = defaultReasoningPolicy(spec.value, draft.max_output_tokens)
    }
    if (spec.value && baseline.reasoning_policy?.mode !== 'selectable') {
      baseline.reasoning_policy = defaultReasoningPolicy(spec.value, baseline.max_output_tokens)
    }
    initial = JSON.stringify(baseline)
  } catch (failure) {
    if (!controller.signal.aborted) catalogError.value = explainConfigError(failure)
  } finally {
    loading.value = false
  }
}
/** 更换目录模型时将输出上限保持在新模型允许的范围内。 */
function changeModel(value?: string): void {
  if (value !== undefined) draft.catalog_model_id = value
  if (!spec.value) return
  draft.max_output_tokens = Math.min(draft.max_output_tokens, spec.value.max_output_tokens)
  draft.reasoning_policy = defaultReasoningPolicy(spec.value, draft.max_output_tokens)
}
/** 保存已校验的模型方案，失败保留草稿和读取版本，不自动测试或设置默认。 */
async function save(): Promise<void> {
  // 无需单独配置默认开关：自动选择允许范围内的目录默认或首个合法档位。
  const body = {
    ...draft,
    reasoning: spec.value
      ? initialReasoning(spec.value, draft.max_output_tokens, policy.value)
      : draft.reasoning,
  }
  error.value = Object.values(validateModel(body, spec.value)).join('；')
  if (error.value || busy.value || loading.value || catalogError.value) return
  busy.value = true
  try {
    await store.saveModel({ ...body, name: draft.name.trim() }, previous)
    emit('close')
  } catch (failure) {
    if (!(failure instanceof DOMException && failure.name === 'AbortError')) {
      error.value = explainConfigError(failure)
      conflict.value = failure instanceof ApiError && failure.code === 40902
      if (conflict.value) await store.load()
    }
  } finally {
    busy.value = false
  }
}
onBeforeUnmount(() => controller.abort())
void load()
</script>
<template>
  <ConfigEditor
    :title="previous ? '编辑模型方案' : '添加模型方案'"
    :dirty="dirty"
    :busy="busy"
    :loading="loading"
    :error="error"
    :conflict="conflict"
    description="设置模型参数与可选强度，让每次提问都有合适的思考空间。"
    :return-focus="returnFocus"
    @submit="save"
    @close="emit('close')"
    @state="emit('state', $event)"
  >
    <div class="model-editor">
      <div class="model-editor-identity">
        <div class="model-editor-brand"><ProviderLogo :provider="provider.provider" /></div>
        <div class="model-editor-identity-text">
          <p class="model-editor-eyebrow">{{ provider.name }}</p>
          <h3>{{ spec?.display_name ?? previous?.catalog?.display_name ?? '选择模型' }}</h3>
          <code>{{ spec?.model_id ?? previous?.catalog_model_id ?? '从供应商目录中选择' }}</code>
        </div>
        <span class="model-editor-seal" aria-hidden="true">知舟</span>
      </div>
      <p v-if="loading" role="status">正在读取模型目录…</p>
      <UiFeedback v-if="catalogError">
        {{ catalogError }}
        <template #actions><UiButton size="sm" @click="load">重试读取目录</UiButton></template>
      </UiFeedback>
      <section class="model-editor-settings" aria-label="模型参数">
        <div class="model-editor-section-title">
          <span aria-hidden="true">01</span>
          <h3>模型参数</h3>
        </div>
        <label v-if="!managed"
          >目录模型<UiSelect
            :model-value="spec ? draft.catalog_model_id : ''"
            name="catalog_model_id"
            :options="catalogOptions"
            :placeholder="`请选择可用模型${previous ? '（原模型可能已不可用）' : ''}`"
            @update:model-value="changeModel"
        /></label>
        <div class="model-editor-fields">
          <label
            >方案名称<UiInput
              v-model="draft.name"
              name="name"
              maxlength="100"
              autocomplete="off"
              placeholder="例如：日常问答、深入思考"
            /><small>显示在聊天的模型列表中。</small></label
          >
          <label
            >最大输出 tokens<UiInput
              v-model.number="draft.max_output_tokens"
              name="max_output_tokens"
              type="number"
              min="1"
              :max="spec?.max_output_tokens"
              step="1"
            /><small v-if="spec"
              >每轮回复上限，最多 {{ spec.max_output_tokens.toLocaleString() }}。</small
            ></label
          >
        </div>
        <UiCheckbox v-if="!managed" v-model="draft.enabled" name="enabled"
          >启用此模型方案</UiCheckbox
        >
      </section>
      <section v-if="spec" class="model-editor-thinking" aria-label="允许的推理强度">
        <div class="model-editor-section-title">
          <span aria-hidden="true">02</span>
          <h3>允许的推理强度</h3>
          <Sparkles :size="16" aria-hidden="true" />
        </div>
        <p>{{ thinkingHint }}</p>
        <ReasoningPolicyEditor
          v-model="policy"
          :model="spec"
          :max-output="draft.max_output_tokens"
        />
        <small class="model-editor-thinking-note">用户在聊天中拖动滑块，自选已勾选的档位。</small>
      </section>
    </div>
  </ConfigEditor>
</template>
<style>
/* 山水留在身份横幅，表单采用清楚的网格；允许强度统一为一组选择，不再叠加默认开关或策略表单。 */
.model-editor {
  min-width: 0;
}
.model-editor-identity {
  position: relative;
  isolation: isolate;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 24px;
  margin-bottom: 26px;
  overflow: hidden;
  border-radius: var(--radius-md);
  background: var(--surface-soft);
  border: 1px solid var(--border);
}
.model-editor-identity::before {
  content: '';
  position: absolute;
  z-index: -1;
  inset: 0;
  opacity: 0.18;
  background: url('@/assets/brand/indigo-ink.png') center 58% / cover;
  mask-image: linear-gradient(to right, transparent, #000);
}
:root[data-theme='dark'] .model-editor-identity::before {
  background-image: url('@/assets/brand/indigo-night.png');
  opacity: 0.3;
}
.model-editor-brand {
  --provider-logo-size: 34px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 54px;
  height: 54px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 15px;
}
.model-editor-identity-text {
  min-width: 0;
}
.model-editor .model-editor-eyebrow {
  margin: 0 0 7px;
  color: var(--text-secondary);
  font-size: 11px;
}
.model-editor-identity h3 {
  margin: 0 0 6px;
  font-size: 23px;
  font-weight: 550;
  letter-spacing: -0.5px;
  overflow-wrap: anywhere;
}
.model-editor-identity code {
  color: var(--text-secondary);
  font: 11px var(--font-mono);
  overflow-wrap: anywhere;
}
.model-editor-seal {
  flex-shrink: 0;
  align-self: flex-start;
  margin-left: auto;
  padding: 4px;
  border: 1px solid var(--brand);
  border-radius: 3px;
  color: var(--brand);
  font-family: var(--font-serif);
  font-size: 12px;
  writing-mode: vertical-rl;
  letter-spacing: 3px;
}
.model-editor-section-title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 18px;
}
.model-editor-section-title > span {
  color: var(--brand);
  font: 10px var(--font-mono);
}
.model-editor-section-title h3 {
  margin: 0;
  color: var(--text);
  font-size: 14px;
  font-weight: 550;
}
.model-editor-section-title svg {
  margin-left: auto;
  color: var(--brand);
}
.model-editor-fields {
  display: grid;
  grid-template-columns: 1.15fr 1fr;
  gap: 22px;
}
.config-fields .model-editor .model-editor-fields > label {
  margin: 0;
}
.model-editor-fields small {
  line-height: 1.65;
}
.model-editor-settings > .ui-checkbox {
  margin-top: 18px;
}
.model-editor-thinking {
  margin-top: 26px;
  padding-top: 22px;
  border-top: 1px solid var(--border);
}
.model-editor-thinking .model-editor-section-title {
  margin-bottom: 10px;
}
.model-editor-thinking p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.8;
}
.model-editor-thinking > small {
  display: block;
  margin-top: 12px;
}
@media (max-width: 540px) {
  .model-editor-identity {
    padding: 18px 16px;
    gap: 12px;
  }
  .model-editor-identity h3 {
    font-size: 20px;
  }
  .model-editor-brand {
    width: 46px;
    height: 46px;
    --provider-logo-size: 28px;
  }
  .model-editor-fields {
    grid-template-columns: minmax(0, 1fr);
    gap: 18px;
  }
}
</style>
