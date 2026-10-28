<!-- 供应商表单：百炼直接粘贴 Base URL，其他供应商使用官方端点；密钥仅在组件内存中短暂保留。 -->
<script setup lang="ts">
import UiInput from '@/shared/components/ui/UiInput.vue'
import UiSelect from '@/shared/components/ui/UiSelect.vue'
import UiCheckbox from '@/shared/components/ui/UiCheckbox.vue'
import { computed, onBeforeUnmount, reactive, ref, toRaw } from 'vue'
import { ApiError } from '@/features/auth/authenticated'
import { explainConfigError, useModelConfigStore } from '../store'
import { formatLabels, normalizeBaseUrl, validateProvider } from '../validation'
import type { ProviderConfiguration, ProviderInput, Provider } from '../types'
import ConfigEditor from './ConfigEditor.vue'
const props = defineProps<{
  previous?: ProviderConfiguration
  brandProvider?: Provider
  returnFocus?: HTMLElement | null
}>()
const emit = defineEmits<{
  close: []
  state: [value: { dirty: boolean; busy: boolean }]
}>()
const store = useModelConfigStore()
// 拷贝原始读取版本，页面刷新不能隐式更新编辑中的并发令牌。
const previous = props.previous ? structuredClone(toRaw(props.previous)) : undefined
const first =
  store.brands.find((item) => item.provider === props.brandProvider) ??
  store.brands.find((item) => item.recommended) ??
  store.brands[0]!
const draft = reactive<ProviderInput>({
  name: previous?.name ?? (props.brandProvider ? first.display_name : ''),
  provider: previous?.provider ?? first.provider,
  api_format: previous?.api_format ?? first.default_api_format,
  endpoint_config: {
    ...(previous?.endpoint_config ??
      (first.provider === 'bailian'
        ? { base_url: '' }
        : { endpoint_id: first.endpoints[0]!.endpoint_id })),
  },
  api_key: '',
  enabled: previous?.enabled ?? true,
})
const initial = JSON.stringify(draft),
  busy = ref(false),
  error = ref(''),
  conflict = ref(false)
const brand = computed(() => store.brands.find((item) => item.provider === draft.provider))
// 下拉只展示服务端支持的接口格式，业务枚举不放入公共控件。
const formatOptions = computed(
  () =>
    brand.value?.api_formats.map((format) => ({ value: format, label: formatLabels[format] })) ??
    [],
)
const endpoint = computed(() =>
  brand.value?.endpoints.find((item) => item.endpoint_id === draft.endpoint_config.endpoint_id),
)
const dirty = computed(() => JSON.stringify(draft) !== initial)
/** 切换供应商时恢复对应格式及地址输入，避免沿用其他品牌的调用目标。 */
function changeProvider(): void {
  draft.api_format = brand.value!.default_api_format
  draft.endpoint_config =
    draft.provider === 'bailian'
      ? { base_url: '' }
      : { endpoint_id: brand.value!.endpoints[0]!.endpoint_id }
}
/** 保存供应商信息，空密钥由状态层省略；冲突时不丢弃当前草稿。 */
async function save(): Promise<void> {
  error.value = Object.values(validateProvider(draft, brand.value, !!previous)).join('；')
  if (error.value || busy.value) return
  busy.value = true
  try {
    await store.saveProvider(
      {
        ...draft,
        name: draft.name.trim(),
        endpoint_config:
          draft.provider === 'bailian'
            ? { base_url: normalizeBaseUrl(draft.endpoint_config.base_url ?? '') }
            : { endpoint_id: draft.endpoint_config.endpoint_id },
      },
      previous,
    )
    draft.api_key = ''
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
onBeforeUnmount(() => {
  draft.api_key = ''
})
</script>
<template>
  <ConfigEditor
    :title="previous ? '编辑供应商配置' : '添加供应商配置'"
    :dirty="dirty"
    :busy="busy"
    :error="error"
    :conflict="conflict"
    description="配置接口与访问密钥，模型启停在供应商面板中管理。"
    :return-focus="returnFocus"
    @submit="save"
    @close="emit('close')"
    @state="emit('state', $event)"
  >
    <section class="config-form-section" aria-label="连接信息">
      <h3>连接信息</h3>
      <label
        >配置名称<UiInput
          v-model="draft.name"
          name="name"
          maxlength="100"
          autocomplete="off"
          placeholder="例如：DeepSeek 官方"
      /></label>
      <label v-if="!brandProvider"
        >供应商<UiSelect
          v-model="draft.provider"
          name="provider"
          :disabled="!!previous"
          :options="
            store.brands.map((item) => ({ value: item.provider, label: item.display_name }))
          "
          @update:model-value="changeProvider"
        /><small v-if="previous">供应商创建后固定，更换时请新建配置。</small></label
      >
      <label v-if="brand && brand.api_formats.length > 1"
        >接口格式<UiSelect
          v-model="draft.api_format"
          name="api_format"
          :options="formatOptions"
        /><small>更改接口格式必须与所有关联方案兼容。</small></label
      >
      <p v-else class="config-hint">接口格式：{{ formatLabels[draft.api_format] }}</p>
      <label v-if="draft.provider === 'bailian'"
        >Base URL<UiInput
          v-model="draft.endpoint_config.base_url"
          name="base_url"
          aria-label="Base URL"
          aria-describedby="bailian-base-url-hint"
          type="url"
          maxlength="2048"
          autocomplete="off"
          spellcheck="false"
          placeholder="https://ws-xxx.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
        /><small id="bailian-base-url-hint"
          >直接复制百炼控制台的“OpenAI 兼容地址”，无需单独填写地域或业务空间。</small
        ></label
      >
      <p v-else class="config-hint">端点：{{ endpoint?.display_name }}</p>
      <UiCheckbox v-if="!brandProvider" v-model="draft.enabled" name="enabled"
        >启用此连接<template #description
          >停用后保留模型方案，聊天中暂不可选。</template
        ></UiCheckbox
      >
    </section>
    <section class="config-form-section" aria-label="访问凭据">
      <h3>访问凭据</h3>
      <label
        >{{ previous ? '替换 API Key · 选填' : 'API Key'
        }}<UiInput
          v-model="draft.api_key"
          name="api_key"
          type="password"
          autocomplete="new-password"
          spellcheck="false"
        /><small>{{
          previous
            ? '留空保留已有密钥；已保存密钥不会回显。'
            : '密钥仅用于本次写入，由后端加密保存。'
        }}</small></label
      >
    </section>
  </ConfigEditor>
</template>
