<!-- 模型方案表单：按供应商及协议读取目录，管理推理联合类型、输出预算与异步目录的释放。 -->
<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, toRaw } from 'vue'
import { ApiError } from '@/features/auth/authenticated'
import UiButton from '@/shared/components/ui/UiButton.vue'
import ConfigEditor from './ConfigEditor.vue'
import { loadCatalog } from '../api'
import { explainConfigError, useModelConfigStore } from '../store'
import { describeReasoning, effortLabels, modeLabels, validateModel } from '../validation'
import type {
  CatalogModel,
  ModelConfiguration,
  ModelInput,
  ProviderConfiguration,
  Reasoning,
} from '../types'
const props = defineProps<{ provider: ProviderConfiguration; previous?: ModelConfiguration }>()
const emit = defineEmits<{ close: []; reload: [] }>()
const store = useModelConfigStore()
const previous = props.previous ? structuredClone(toRaw(props.previous)) : undefined
const draft = reactive<ModelInput>({
  name: previous?.name ?? '',
  provider_configuration_id: props.provider.id,
  catalog_model_id: previous?.catalog_model_id ?? '',
  reasoning: previous ? { ...previous.reasoning } : { mode: 'default' },
  max_output_tokens: previous?.max_output_tokens ?? 16384,
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
/** 读取匹配协议的目录，失败只影响当前抽屉，并提供显式重试。 */
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
    if (!previous && !draft.catalog_model_id) {
      draft.catalog_model_id = data.find((item) => item.available)?.catalog_model_id ?? ''
      changeModel()
      initial = JSON.stringify(draft)
    }
  } catch (failure) {
    if (!controller.signal.aborted) catalogError.value = explainConfigError(failure)
  } finally {
    loading.value = false
  }
}
/** 更换目录模型时重置为其合法默认推理值，输出保留在新模型允许的范围内。 */
function changeModel(event?: Event): void {
  if (event) draft.catalog_model_id = (event.target as HTMLSelectElement).value
  if (!spec.value) return
  draft.reasoning = spec.value.reasoning.allowed_modes.includes('default')
    ? { mode: 'default' }
    : { ...spec.value.reasoning.default }
  draft.max_output_tokens = Math.min(draft.max_output_tokens, spec.value.max_output_tokens)
}
/** 切换推理形式时只保留该联合分支允许的参数。 */
function changeMode(event: Event): void {
  const mode = (event.target as HTMLSelectElement).value as Reasoning['mode']
  if (mode === 'effort')
    draft.reasoning = { mode, effort: spec.value!.reasoning.effort_options[0]! }
  else if (mode === 'budget') {
    const limits = spec.value!.reasoning.budget!
    draft.reasoning = { mode, budget_tokens: Math.min(limits.max, Math.max(limits.min, 4096)) }
  } else draft.reasoning = { mode }
}
/** 保存已校验的模型方案，失败保留草稿和读取版本，不自动测试或设置默认。 */
async function save(): Promise<void> {
  error.value = Object.values(validateModel(draft, spec.value)).join('；')
  if (error.value || busy.value || loading.value || catalogError.value) return
  busy.value = true
  try {
    await store.saveModel(
      { ...draft, name: draft.name.trim(), reasoning: { ...draft.reasoning } },
      previous,
    )
    emit('close')
  } catch (failure) {
    if (!(failure instanceof DOMException && failure.name === 'AbortError')) {
      error.value = explainConfigError(failure)
      conflict.value = failure instanceof ApiError && failure.code === 40902
    }
  } finally {
    busy.value = false
  }
}
/** 显式刷新列表并重建表单，用户重新基于最新实体编辑。 */
async function reload(): Promise<void> {
  await store.load()
  if (!store.loadError) emit('reload')
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
    @submit="save"
    @close="emit('close')"
    @reload="reload"
  >
    <p class="config-hint">关联供应商：{{ provider.name }}；归属创建后固定。</p>
    <p v-if="loading" role="status">正在读取模型目录…</p>
    <p v-if="catalogError" class="config-error" role="alert">
      {{ catalogError }} <UiButton size="sm" @click="load">重试读取目录</UiButton>
    </p>
    <label
      >方案名称<input
        v-model="draft.name"
        name="name"
        maxlength="100"
        autocomplete="off"
        placeholder="例如：日常问答、深入思考"
    /></label>
    <label
      >目录模型<select
        :value="spec ? draft.catalog_model_id : ''"
        name="catalog_model_id"
        @change="changeModel"
      >
        <option v-if="!spec" value="" disabled>
          请选择可用模型{{ previous ? '（原模型可能已不可用）' : '' }}
        </option>
        <option
          v-for="item in entries"
          :key="item.catalog_model_id"
          :value="item.catalog_model_id"
          :disabled="!item.available"
        >
          {{ item.display_name }}{{ item.available ? '' : ' · 不可用' }}
        </option></select
      ><small>仅展示与当前供应商及接口格式匹配的模型。</small></label
    >
    <template v-if="spec">
      <label
        >推理方式<select :value="draft.reasoning.mode" name="reasoning_mode" @change="changeMode">
          <option
            v-if="
              draft.reasoning.mode === 'default' &&
              !spec.reasoning.allowed_modes.includes('default')
            "
            value="default"
          >
            模型默认 · {{ describeReasoning(spec.reasoning.default) }}
          </option>
          <option v-for="mode in spec.reasoning.allowed_modes" :key="mode" :value="mode">
            {{ modeLabels[mode] }}
          </option></select
        ><small v-if="draft.reasoning.mode === 'default'"
          >目录默认：{{ describeReasoning(spec.reasoning.default) }}</small
        ></label
      >
      <label v-if="draft.reasoning.mode === 'effort'"
        >推理档位<select v-model="draft.reasoning.effort" name="effort">
          <option v-for="effort in spec.reasoning.effort_options" :key="effort" :value="effort">
            {{ effortLabels[effort] ?? effort }} · {{ effort }}
          </option>
        </select></label
      >
      <label v-if="draft.reasoning.mode === 'budget' && spec.reasoning.budget"
        >思考预算（tokens）<input
          v-model.number="draft.reasoning.budget_tokens"
          name="budget_tokens"
          type="number"
          :min="spec.reasoning.budget.min"
          :max="spec.reasoning.budget.max"
          step="1"
        /><small
          >范围 {{ spec.reasoning.budget.min }}–{{ spec.reasoning.budget.max
          }}{{ spec.reasoning.budget_must_fit_output ? '，且须小于最大输出 tokens' : '' }}。</small
        ></label
      >
      <label
        >最大输出 tokens<input
          v-model.number="draft.max_output_tokens"
          name="max_output_tokens"
          type="number"
          min="1"
          :max="spec.max_output_tokens"
          step="1"
        /><small>最大允许 {{ spec.max_output_tokens.toLocaleString() }}。</small></label
      >
    </template>
  </ConfigEditor>
</template>
