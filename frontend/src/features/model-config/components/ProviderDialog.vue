<!-- 供应商配置弹窗：统一连接编辑、目录模型启停、旧方案与草稿的生命周期。 -->
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { useAuthStore } from '@/features/auth/store'
import UiModal from '@/shared/components/ui/UiModal.vue'
import UiConfirmDialog from '@/shared/components/ui/UiConfirmDialog.vue'
import UiButton from '@/shared/components/ui/UiButton.vue'
import { Plus } from '@lucide/vue'
import ProviderConnectionCard from './ProviderConnectionCard.vue'
import ProviderEditor from './ProviderEditor.vue'
import ModelEditor from './ModelEditor.vue'
import CatalogModelRow from './CatalogModelRow.vue'
import { catalogRows, initialModel } from '../catalog-rows'
import type { CatalogRow } from '../catalog-rows'
import { loadCatalog } from '../api'
import { explainConfigError, useModelConfigStore } from '../store'
import type {
  CatalogModel,
  ProviderInfo,
  ModelConfiguration,
  ProviderConfiguration,
} from '../types'
const props = defineProps<{ brand: ProviderInfo }>()
const emit = defineEmits<{ close: [] }>()
const store = useModelConfigStore()
const auth = useAuthStore()
const connections = computed(() =>
  store.configurations.filter((item) => item.provider === props.brand.provider),
)
const selectedId = ref(
  connections.value.find((item) => item.id === store.selectedProvider)?.id ??
    connections.value[0]?.id ??
    '',
)
const current = computed(() => connections.value.find((item) => item.id === selectedId.value))
const models = computed(() =>
  store.models.filter((item) => item.provider_configuration_id === current.value?.id),
)
const catalog = ref<CatalogModel[]>([])
const loading = ref(false),
  catalogError = ref(''),
  error = ref(''),
  busy = ref(false)
const rows = computed(() => catalogRows(catalog.value, models.value))
const edit = ref<{ kind: 'provider' | 'model'; id?: string; key: number } | null>(null)
const editingProvider = computed(() => connections.value.find((item) => item.id === edit.value?.id))
const editingModel = computed(() => models.value.find((item) => item.id === edit.value?.id))
const editState = ref({ dirty: false, busy: false })
const editTrigger = shallowRef<HTMLElement | null>(null)
const locked = computed(() => busy.value || editState.value.busy || store.loading)
const confirmation = ref<{
  title: string
  description: string
  label: string
  perform: () => void | Promise<void>
} | null>(null)
const catalogRevision = ref(0)
let editKey = 0

/** 读取当前连接格式的目录，切换或卸载时取消旧请求，拒绝迟到结果。 */
watch(
  [() => current.value?.id, () => current.value?.api_format, catalogRevision],
  async (_, __, cleanup) => {
    const controller = new AbortController()
    cleanup(() => controller.abort())
    catalog.value = []
    catalogError.value = ''
    loading.value = true
    try {
      const entries = await loadCatalog(
        props.brand.provider,
        current.value?.api_format ?? props.brand.default_api_format,
        controller.signal,
      )
      if (!controller.signal.aborted) catalog.value = entries
    } catch (failure) {
      if (!controller.signal.aborted) catalogError.value = explainConfigError(failure)
    } finally {
      if (!controller.signal.aborted) loading.value = false
    }
  },
  { immediate: true },
)

/** 清除已关闭编辑器的状态，避免旧草稿标记阻止后续操作。 */
function endEdit(): void {
  edit.value = null
  editState.value = { dirty: false, busy: false }
}
/** 在关闭、切换连接或编辑目标前保护当前草稿；保存期间禁止切换。 */
function guard(action: () => void): void {
  if (locked.value) return
  if (!editState.value.dirty) {
    action()
    return
  }
  confirmation.value = {
    title: '放弃未保存的更改？',
    description: '本次填写的内容不会保存。',
    label: '放弃更改',
    perform: action,
  }
}
/** 打开独立的连接或模型编辑弹窗，保留主面板及当前连接选择。 */
function openEditor(kind: 'provider' | 'model', id?: string): void {
  // 在修改 edit 导致按钮禁用之前记录入口；关闭子弹窗后仍能回到该卡片。
  const trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null
  guard(() => {
    endEdit()
    editTrigger.value = trigger
    if (kind === 'provider' && id) {
      selectedId.value = id
      store.selectedProvider = id
    }
    edit.value = { kind, id, key: ++editKey }
  })
}
/** 切换当前品牌内的连接，每份连接使用独立的模型状态。 */
function changeConnection(next: string): void {
  if (next === selectedId.value) return
  guard(() => {
    endEdit()
    selectedId.value = next
    store.selectedProvider = next
  })
}
/** 结束连接编辑并定位已保存的连接，取消时保留供应商面板和新增入口。 */
function providerSaved(): void {
  if (connections.value.some((item) => item.id === store.selectedProvider))
    selectedId.value = store.selectedProvider
  endEdit()
}
/** 执行一次显式写入，失败保留原状态并同步快照；不维护列表底部的操作通知。 */
async function execute(work: () => Promise<void>): Promise<void> {
  if (locked.value) return
  busy.value = true
  error.value = ''
  try {
    await work()
  } catch (failure) {
    if (!(failure instanceof DOMException && failure.name === 'AbortError')) {
      error.value = explainConfigError(failure)
      await store.load()
    }
  } finally {
    busy.value = false
  }
}
/** 首次开启自动保存目录默认；已有方案只改启停，保留身份及用户参数。 */
function toggle(row: CatalogRow): void {
  const connection = current.value
  if (!connection || loading.value || catalogError.value || edit.value) return
  if (row.model) {
    const model = row.model
    void execute(() => store.setEnabled('model', model, !model.enabled))
  } else if (row.catalog?.available) {
    const entry = row.catalog
    void execute(() => store.saveModel(initialModel(connection.id, entry)))
  }
}
/** 独立启停指定连接，不切换当前选择，也不改关联模型的启用标记。 */
function toggleConnection(connection: ProviderConfiguration): void {
  void execute(() => store.setEnabled('provider', connection, !connection.enabled))
}
/** 保持默认选择显式，启停与高级参数保存都不触发此操作。 */
function select(model: ModelConfiguration): void {
  void execute(() => store.setDefault(model.id))
}
/** 立即清除全局默认，保留已有会话的独立模型选择。 */
function clearDefault(): void {
  void execute(() => store.setDefault(null))
}
/** 删除前保留引用限制及不可撤销提示，目录项在删除后重新显示为关闭。 */
function remove(
  kind: 'provider' | 'model',
  item: ProviderConfiguration | ModelConfiguration,
): void {
  if (locked.value || edit.value) return
  if (
    kind === 'provider' &&
    store.models.some((model) => model.provider_configuration_id === item.id)
  ) {
    error.value = '供应商配置仍被引用，请先删除该连接下的全部模型方案。'
    return
  }
  confirmation.value = {
    title: `删除${kind === 'provider' ? '供应商配置' : '模型方案'}？`,
    description:
      (kind === 'model' && store.selected?.model_configuration_id === item.id
        ? '将自动清除全局默认并删除“'
        : '将删除“') +
      item.name +
      '”。已有聊天历史会保留；此操作不能撤销。',
    label: '确认删除',
    perform: () =>
      execute(async () => {
        await store.remove(kind, item)
        if (kind === 'provider' && selectedId.value === item.id) {
          selectedId.value = connections.value[0]?.id ?? ''
        }
      }),
  }
}
/** 直接测试模型连接，由统一执行锁防止重复请求，结果显示在原模型卡片。 */
function test(model: ModelConfiguration): void {
  void execute(() => store.test(model.id))
}
/** 确认后先释放确认层，再执行原先受保护的动作。 */
function confirm(): void {
  const action = confirmation.value?.perform
  confirmation.value = null
  void action?.()
}
/** 关闭供应商弹窗前保护正在保存的操作和未保存草稿。 */
function close(): void {
  guard(() => emit('close'))
}
// 编辑弹窗负责草稿离页确认，供应商弹窗额外阻止启停写入期间的主动导航。
onBeforeRouteLeave(() => !auth.isAuthenticated || !busy.value)
onBeforeUnmount(() => store.cancelManagement())
</script>
<template>
  <UiModal
    :open="true"
    :title="brand.display_name"
    description="配置连接，开启你需要的模型。"
    wide
    :close-disabled="locked"
    @update:open="close"
  >
    <div class="provider-dialog-layout">
      <section class="provider-connection-panel" aria-label="供应商连接">
        <div class="config-section-heading">
          <div>
            <p class="config-eyebrow">CONNECTIONS</p>
            <h2>
              供应商连接 <small>{{ connections.length }}</small>
            </h2>
          </div>
          <UiButton
            size="sm"
            variant="ghost"
            :disabled="locked || (edit?.kind === 'provider' && !edit.id)"
            @click="openEditor('provider')"
          >
            <Plus :size="14" aria-hidden="true" />添加连接
          </UiButton>
        </div>
        <p class="provider-panel-caption">选择连接，管理对应的模型。</p>
        <div class="provider-connection-list">
          <ProviderConnectionCard
            v-for="connection in connections"
            :key="connection.id"
            :connection="connection"
            :selected="connection.id === selectedId"
            :busy="locked"
            :blocked="!!edit"
            @select="changeConnection(connection.id)"
            @toggle="toggleConnection(connection)"
            @edit="openEditor('provider', connection.id)"
            @delete="remove('provider', connection)"
          />
        </div>
        <button
          v-if="!connections.length"
          type="button"
          class="provider-connection-empty"
          aria-label="添加首个供应商连接"
          :disabled="locked || !!edit"
          @click="openEditor('provider')"
        >
          <Plus :size="24" aria-hidden="true" />
          <strong>还没有连接</strong>
          <span>点击添加连接，配置接口与密钥后即可开启模型。</span>
        </button>
      </section>
      <section class="provider-models" aria-label="关联模型方案">
        <div class="config-section-heading">
          <div>
            <p class="config-eyebrow">MODELS</p>
            <h2>
              模型 <small>{{ rows.length }}</small>
            </h2>
          </div>
          <span class="config-hint">按需开启，即刻保存</span>
        </div>
        <p class="provider-panel-caption">
          {{
            !current
              ? '请先保存连接信息，再开启模型。'
              : !current.enabled
                ? '连接已停用；模型各自的启用状态会保留。'
                : current.name + ' · 启停自动保存，停用不影响已有历史。'
          }}
        </p>
        <p v-if="store.loadError && !error" class="config-error" role="alert">
          配置暂未同步：{{ store.loadError }}。
        </p>
        <p v-if="error" class="config-error" role="alert">
          {{ error }}
        </p>
        <p v-if="loading" role="status" class="config-hint">正在读取模型目录…</p>
        <p v-if="catalogError" role="alert" class="config-error">
          {{ catalogError }} <UiButton size="sm" @click="catalogRevision++">重试读取目录</UiButton>
        </p>
        <div class="catalog-model-list">
          <CatalogModelRow
            v-for="row in rows"
            :key="row.key"
            :row="row"
            :connected="!!current"
            :provider-enabled="!!current?.enabled"
            :provider-version="current?.version ?? 0"
            :current="store.selected?.model_configuration_id === row.model?.id"
            :busy="locked || loading || !!catalogError || !!edit"
            :editing="edit?.id === row.model?.id && edit?.kind === 'model'"
            :test="row.model ? store.tests[row.model.id] : undefined"
            @toggle="toggle(row)"
            @select="row.model && select(row.model)"
            @clear="clearDefault"
            @edit="row.model && openEditor('model', row.model.id)"
            @delete="row.model && remove('model', row.model)"
            @test="row.model && test(row.model)"
          />
        </div>
        <p v-if="!loading && !catalogError && !rows.length" class="config-hint">
          当前接口格式下没有可用模型。
        </p>
      </section>
    </div>
    <ProviderEditor
      v-if="edit?.kind === 'provider'"
      :key="edit.key"
      :previous="editingProvider"
      :brand-provider="brand.provider"
      :return-focus="editTrigger"
      @state="editState = $event"
      @close="providerSaved"
    />
    <ModelEditor
      v-if="edit?.kind === 'model' && current && editingModel"
      :key="edit.key"
      :provider="current"
      :previous="editingModel"
      managed
      :return-focus="editTrigger"
      @state="editState = $event"
      @close="endEdit"
    />
    <UiConfirmDialog
      v-if="confirmation"
      :open="true"
      :title="confirmation.title"
      :description="confirmation.description"
      :confirm-label="confirmation.label"
      :cancel-label="confirmation.label === '放弃更改' ? '继续编辑' : '取消'"
      @update:open="confirmation = null"
      @confirm="confirm"
    />
  </UiModal>
</template>
