<!-- 模型管理页面：编排供应商/模型联动、写入确认和表单；业务状态与 HTTP 由 model-config 模块负责。 -->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ArrowLeft, Plus, SlidersHorizontal, Layers } from '@lucide/vue'
import { explainConfigError, useModelConfigStore } from '@/features/model-config/store'
import { formatLabels } from '@/features/model-config/validation'
import type { ModelConfiguration, ProviderConfiguration } from '@/features/model-config/types'
import ProviderEditor from '@/features/model-config/components/ProviderEditor.vue'
import ModelEditor from '@/features/model-config/components/ModelEditor.vue'
import ModelCard from '@/features/model-config/components/ModelCard.vue'
import UiButton from '@/shared/components/ui/UiButton.vue'
import UiModal from '@/shared/components/ui/UiModal.vue'
import '@/features/model-config/model-config.css'

const store = useModelConfigStore()
const current = computed(() =>
  store.configurations.find((item) => item.id === store.selectedProvider),
)
const models = computed(() =>
  store.models.filter((item) => item.provider_configuration_id === current.value?.id),
)
const currentBrand = computed(() =>
  store.brands.find((item) => item.provider === current.value?.provider),
)
const currentEndpoint = computed(() =>
  currentBrand.value?.endpoints.find(
    (item) => item.endpoint_id === current.value?.endpoint_config.endpoint_id,
  ),
)
const editor = ref<{ kind: 'provider' | 'model'; id?: string; key: number } | null>(null)
const providerEditing = computed(() =>
  store.configurations.find((item) => item.id === editor.value?.id),
)
const modelEditing = computed(() => store.models.find((item) => item.id === editor.value?.id))
const busy = ref(false),
  error = ref(''),
  notice = ref('')
const confirmation = ref<{
  title: string
  description: string
  label: string
  danger?: boolean
  perform?: () => Promise<void>
} | null>(null)
let editorKey = 0
/** 打开一个具有独立草稿和读取版本的表单。 */
function edit(kind: 'provider' | 'model', id?: string): void {
  if (store.loading || busy.value) return
  editor.value = { kind, id, key: ++editorKey }
  error.value = ''
  notice.value = ''
}
/** 读取最新版本后重建编辑器；明确的重建才允许舍弃冲突草稿。 */
function reloadEditor(): void {
  if (!editor.value) return
  if (
    editor.value.id &&
    !(editor.value.kind === 'provider' ? providerEditing.value : modelEditing.value)
  ) {
    editor.value = null
    error.value = '配置已不存在，请从最新列表中重新选择'
    return
  }
  editor.value = { ...editor.value, key: ++editorKey }
}
/** 执行已获得明确用户操作的写入，失败保留当前资源与可重试错误。 */
async function execute(work: () => Promise<void>, message: string): Promise<void> {
  if (busy.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await work()
    notice.value = message
    confirmation.value = null
  } catch (failure) {
    if (!(failure instanceof DOMException && failure.name === 'AbortError'))
      error.value = explainConfigError(failure)
  } finally {
    busy.value = false
  }
}
/** 切换全局默认，允许不经过上游测试直接选择有效方案。 */
function select(model: ModelConfiguration): void {
  void execute(
    () => store.setDefault(model.id),
    `已将“${model.name}”设为全局默认，用于尚未选择模型的会话。`,
  )
}
/** 删除前检查可见引用并确认；真正写入仍由服务端校验版本和引用。 */
function remove(
  kind: 'provider' | 'model',
  item: ProviderConfiguration | ModelConfiguration,
): void {
  error.value = ''
  if (
    kind === 'provider' &&
    store.models.some((model) => model.provider_configuration_id === item.id)
  ) {
    confirmation.value = {
      title: '供应商配置仍被引用',
      description: '请先删除该供应商配置下的全部模型方案，再删除供应商配置。',
      label: '知道了',
    }
    return
  }
  if (kind === 'model' && store.selected?.model_configuration_id === item.id) {
    confirmation.value = {
      title: '当前默认方案不能直接删除',
      description: '请先切换或清除全局默认，再删除这个模型方案。',
      label: '知道了',
    }
    return
  }
  confirmation.value = {
    title: `删除${kind === 'provider' ? '供应商配置' : '模型方案'}？`,
    description: `将删除“${item.name}”。已有聊天历史会保留；此操作不能撤销。`,
    label: '确认删除',
    danger: true,
    perform: () => store.remove(kind, item),
  }
}
/** 显式提示清除默认将影响所有用户后续聊天。 */
function clearDefault(): void {
  error.value = ''
  confirmation.value = {
    title: '清除全局默认模型？',
    description:
      '清除后，新会话需要手动选择可用模型。所有用户的已有会话选择、正在生成的回复和历史不受影响。',
    label: '清除默认',
    danger: true,
    perform: () => store.setDefault(null),
  }
}
/** 主动测试前说明调用费用和验证边界，保存与默认设置都不会触发此调用。 */
function test(model: ModelConfiguration): void {
  error.value = ''
  confirmation.value = {
    title: '测试模型连接',
    description:
      '将发起一次短文本流请求，可能产生供应商费用。不会调用业务工具、创建聊天历史或自动设置默认。',
    label: '开始测试',
    perform: () => store.test(model.id),
  }
}
/** 确认当前弹窗中的具体动作，信息提示类弹窗只关闭自身。 */
function confirm(): void {
  const work = confirmation.value?.perform
  if (!work) confirmation.value = null
  else void execute(work, '操作已完成')
}
/** 关闭确认弹窗；写入进行中保持可见，避免重复提交。 */
function closeConfirmation(): void {
  if (!busy.value) {
    confirmation.value = null
    error.value = ''
  }
}
/** 定位默认方案所在的供应商，保留当前管理页。 */
function locateDefault(): void {
  const id = store.selected?.model?.provider_configuration_id
  if (id) store.selectedProvider = id
}
/** 启停只修改当前资源，停用前说明影响，不级联改写关联方案或默认引用。 */
function toggle(
  kind: 'provider' | 'model',
  item: ProviderConfiguration | ModelConfiguration,
): void {
  const enabled = !item.enabled
  if (enabled) {
    void execute(() => store.setEnabled(kind, item, true), '已启用，可用于符合条件的聊天选择')
    return
  }
  confirmation.value = {
    title: kind === 'provider' ? '停用供应商连接？' : '停用模型方案？',
    description:
      '停用后暂时不能在聊天中选择，相关会话下次发送需重新选择。已有配置、默认引用和历史会保留，正在生成的回复不受影响。',
    label: '确认停用',
    perform: () => store.setEnabled(kind, item, false),
  }
}
onMounted(() => {
  void store.load()
})
onBeforeUnmount(() => store.cancelManagement())
</script>
<template>
  <section class="model-management-main" aria-label="模型管理工作区">
    <div class="config-page">
      <header class="model-management-heading">
        <div>
          <h1 tabindex="-1">模型管理</h1>
          <p class="config-hint">管理供应商连接与模型方案，为聊天选择合适的默认模型。</p>
        </div>
        <div class="config-actions">
          <UiButton size="sm" :loading="store.loading" :disabled="busy" @click="store.load"
            >刷新配置</UiButton
          ><RouterLink to="/" class="config-link"><ArrowLeft :size="16" />返回聊天</RouterLink>
        </div>
      </header>
      <p v-if="store.loadError" class="config-error" role="alert">
        {{ store.loadError }}，请刷新配置后重试。
      </p>
      <p v-if="error && !confirmation" class="config-error" role="alert">
        {{ error }} <UiButton size="sm" @click="store.load">读取最新配置</UiButton>
      </p>
      <p v-if="notice" class="config-notice" role="status">{{ notice }}</p>
      <p v-if="store.loading && !store.selected" role="status">正在读取模型配置…</p>
      <section v-if="store.selected" class="config-default" aria-label="全局默认模型">
        <div class="config-default-summary">
          <span class="config-default-icon" aria-hidden="true"
            ><SlidersHorizontal :size="21"
          /></span>
          <div>
            <p class="config-eyebrow">全局默认模型</p>
            <h2>
              {{ store.selected.model?.name ?? '还没有默认模型'
              }}<span
                v-if="store.selected.model && !store.selected.model.selectable"
                class="config-badge config-badge--invalid"
                >不可用</span
              >
            </h2>
            <p v-if="store.selected.model" class="config-hint">
              {{ store.selected.model.catalog?.display_name ?? '请编辑方案，选择可用模型' }}
            </p>
            <p v-else class="config-hint">
              {{
                store.models.length
                  ? '选择一个模型方案，设为默认即可开始聊天。'
                  : '添加供应商连接与模型方案后，即可设为默认。'
              }}
            </p>
          </div>
        </div>
        <div class="config-default-context">
          <div v-if="store.selected.model" class="config-actions">
            <UiButton size="sm" @click="locateDefault">查看方案</UiButton
            ><UiButton
              variant="ghost"
              size="sm"
              :disabled="busy || store.loading"
              @click="clearDefault"
              >清除默认</UiButton
            >
          </div>
          <p class="config-hint">所有登录用户共享 · 默认仅初始化尚无选择的会话</p>
        </div>
      </section>
      <div class="config-management-grid">
        <section class="config-provider-panel" aria-label="供应商配置列表">
          <div class="config-section-heading">
            <h2>
              供应商配置 <small>{{ store.configurations.length }}</small>
            </h2>
            <UiButton
              variant="ghost"
              size="sm"
              :disabled="store.loading || !store.brands.length || busy"
              @click="edit('provider')"
              ><Plus :size="15" />添加</UiButton
            >
          </div>
          <div class="config-provider-list">
            <button
              v-for="provider in store.configurations"
              :key="provider.id"
              type="button"
              :aria-pressed="provider.id === store.selectedProvider"
              @click="store.selectedProvider = provider.id"
            >
              <strong
                >{{ provider.name
                }}<span v-if="!provider.enabled" class="config-badge config-badge--invalid"
                  >已停用</span
                ></strong
              ><small
                >{{
                  store.brands.find((item) => item.provider === provider.provider)?.display_name
                }}
                ·
                {{
                  store.models.filter((item) => item.provider_configuration_id === provider.id)
                    .length
                }}
                个方案</small
              >
            </button>
          </div>
          <label v-if="store.configurations.length" class="config-provider-mobile"
            >当前供应商配置<select v-model="store.selectedProvider">
              <option
                v-for="provider in store.configurations"
                :key="provider.id"
                :value="provider.id"
              >
                {{ provider.name }}
              </option>
            </select></label
          >
          <p class="config-hint">一份密钥，可复用多套模型方案。</p>
        </section>
        <section class="config-model-panel" aria-label="关联模型方案">
          <template v-if="current"
            ><header class="config-provider-summary">
              <div class="config-section-heading">
                <h2>
                  {{ current.name
                  }}<span v-if="!current.enabled" class="config-badge config-badge--invalid"
                    >已停用</span
                  >
                </h2>
                <span class="config-badge">{{
                  current.api_key_configured ? '密钥已配置' : '密钥未配置'
                }}</span>
              </div>
              <p class="config-hint">
                {{ currentBrand?.display_name }} · {{ formatLabels[current.api_format] }}
                <code v-if="current.endpoint_config.base_url" class="config-endpoint-url">{{
                  current.endpoint_config.base_url
                }}</code>
                <template v-else> · {{ currentEndpoint?.display_name }}</template>
              </p>
              <div class="config-actions">
                <UiButton
                  variant="ghost"
                  size="sm"
                  :disabled="busy || store.loading"
                  @click="edit('provider', current.id)"
                  >编辑供应商</UiButton
                ><UiButton
                  variant="ghost"
                  size="sm"
                  :disabled="busy || store.loading"
                  @click="toggle('provider', current)"
                  >{{ current.enabled ? '停用连接' : '启用连接' }}</UiButton
                ><UiButton
                  variant="ghost"
                  size="sm"
                  class="config-danger"
                  :disabled="busy || store.loading"
                  @click="remove('provider', current)"
                  >删除供应商</UiButton
                >
              </div>
            </header>
            <div class="config-section-heading">
              <h2>
                模型方案 <small>{{ models.length }}</small>
              </h2>
              <UiButton
                v-if="models.length"
                variant="primary"
                size="sm"
                :disabled="busy || store.loading"
                @click="edit('model')"
                ><Plus :size="15" />添加模型方案</UiButton
              >
            </div>
            <div v-if="models.length" class="config-model-grid">
              <ModelCard
                v-for="model in models"
                :key="model.id"
                :model="model"
                :provider-version="current.version"
                :current="store.selected?.model_configuration_id === model.id"
                :busy="busy || store.loading"
                :test="store.tests[model.id]"
                @test="test(model)"
                @select="select(model)"
                @edit="edit('model', model.id)"
                @delete="remove('model', model)"
                @toggle="toggle('model', model)"
              />
            </div>
            <div v-if="!models.length" class="config-empty">
              <span class="config-empty-icon" aria-hidden="true"><Layers :size="26" /></span>
              <h2>为这份连接添加第一个模型</h2>
              <p>连接已保存，继续选择模型并配置推理参数。</p>
              <UiButton variant="primary" :disabled="busy || store.loading" @click="edit('model')"
                >添加模型方案</UiButton
              >
            </div></template
          >
          <div v-else-if="!store.loading && !store.loadError" class="config-empty">
            <span class="config-empty-icon" aria-hidden="true"
              ><SlidersHorizontal :size="26"
            /></span>
            <h2>从一份供应商配置开始</h2>
            <p>选择官方供应商，保存连接信息，再添加模型方案。</p>
            <UiButton variant="primary" :disabled="!store.brands.length" @click="edit('provider')"
              >添加供应商配置</UiButton
            >
          </div>
          <p class="config-hint">保存只更新配置；测试由你主动发起，也可以直接设置默认。</p>
        </section>
      </div>
      <ProviderEditor
        v-if="editor?.kind === 'provider'"
        :key="editor.key"
        :previous="providerEditing"
        @close="editor = null"
        @reload="reloadEditor"
      />
      <ModelEditor
        v-if="editor?.kind === 'model' && current"
        :key="editor.key"
        :provider="current"
        :previous="modelEditing"
        @close="editor = null"
        @reload="reloadEditor"
      />
      <UiModal
        v-if="confirmation"
        :open="true"
        :title="confirmation.title"
        :description="confirmation.description"
        @update:open="closeConfirmation"
        ><p v-if="error" class="config-error" role="alert">
          {{ error }} <UiButton size="sm" :disabled="busy" @click="store.load">刷新配置</UiButton>
        </p>
        <div class="config-actions config-confirm-actions">
          <UiButton v-if="confirmation.perform" :disabled="busy" @click="closeConfirmation"
            >取消</UiButton
          ><UiButton
            :class="{ 'config-danger': confirmation.danger }"
            :loading="busy"
            @click="confirm"
            >{{ confirmation.label }}</UiButton
          >
        </div></UiModal
      >
    </div>
  </section>
</template>
