<!-- 模型目录行：以受控开关展示已保存状态，高级设置和有副作用的操作由弹窗协调。 -->
<script setup lang="ts">
import UiFeedback from '@/shared/components/ui/UiFeedback.vue'
import UiTag from '@/shared/components/ui/UiTag.vue'
import { computed } from 'vue'
import { FlaskConical, Settings2, Star, Trash2 } from '@lucide/vue'
import UiSwitch from '@/shared/components/ui/UiSwitch.vue'
import UiButton from '@/shared/components/ui/UiButton.vue'
import type { CatalogRow } from '../catalog-rows'
import type { TestResult } from '../types'
import { describeReasoning } from '../validation'
const props = defineProps<{
  row: CatalogRow
  connected: boolean
  providerEnabled: boolean
  providerVersion: number
  current: boolean
  busy: boolean
  editing: boolean
  test?: { running: boolean; result?: TestResult; error?: string }
}>()
defineEmits<{ toggle: []; select: []; clear: []; edit: []; test: []; delete: [] }>()
const title = computed(() => props.row.model?.name ?? props.row.catalog?.display_name ?? '')
const available = computed(() =>
  props.row.model ? props.row.model.available : !!props.row.catalog?.available,
)
const stale = computed(
  () =>
    !!props.test?.result &&
    (props.test.result.model_version !== props.row.model?.version ||
      props.test.result.provider_configuration_version !== props.providerVersion),
)
</script>
<template>
  <article
    class="catalog-model-row"
    :class="{ 'is-enabled': row.model?.enabled }"
    :aria-label="`模型方案：${title}`"
  >
    <div class="catalog-model-main">
      <div class="catalog-model-identity">
        <h3>{{ title }} <UiTag size="xs" v-if="current" tone="brand">当前默认</UiTag></h3>
        <p class="config-model-id">
          {{ row.catalog?.model_id ?? row.model?.catalog?.model_id ?? row.model?.catalog_model_id }}
        </p>
        <UiTag
          size="sm"
          :tone="available && row.model?.enabled && providerEnabled ? 'brand' : 'neutral'"
          dot
          >{{
            !available
              ? '当前不可用'
              : row.model?.enabled
                ? providerEnabled
                  ? '已启用'
                  : '已启用 · 连接已停用'
                : '已停用'
          }}</UiTag
        >
      </div>
      <UiSwitch
        :model-value="!!row.model?.enabled"
        :label="`启用模型 ${title}`"
        :disabled="busy || !connected || (!available && !row.model?.enabled)"
        :busy="busy"
        @update:model-value="$emit('toggle')"
      />
    </div>
    <div v-if="row.model" class="catalog-model-footer">
      <p class="config-model-options">
        {{ describeReasoning(row.model.reasoning) }} · 输出上限
        {{ row.model.max_output_tokens.toLocaleString() }}
      </p>
      <div class="catalog-model-tools" role="group" :aria-label="title + '的模型操作'">
        <UiButton
          v-if="!current"
          size="sm"
          variant="ghost"
          :disabled="busy || !row.model.selectable"
          @click="$emit('select')"
          ><Star :size="13" aria-hidden="true" />设为默认</UiButton
        >
        <UiButton v-else size="sm" variant="ghost" :disabled="busy" @click="$emit('clear')"
          ><Star :size="13" aria-hidden="true" />清除默认</UiButton
        >
        <UiButton
          size="sm"
          variant="ghost"
          :disabled="busy"
          :aria-expanded="editing"
          @click="$emit('edit')"
          ><Settings2 :size="13" aria-hidden="true" />高级设置</UiButton
        >
        <UiButton
          size="sm"
          variant="ghost"
          :disabled="busy || !available"
          :loading="test?.running"
          @click="$emit('test')"
          ><FlaskConical :size="13" aria-hidden="true" />测试</UiButton
        >
        <UiButton size="sm" variant="danger" :disabled="busy" @click="$emit('delete')"
          ><Trash2 :size="13" aria-hidden="true" />删除</UiButton
        >
      </div>
    </div>
    <div v-if="test?.running || test?.result || test?.error" class="catalog-test-feedback">
      <p v-if="test?.running" role="status" class="config-hint">正在测试文本流…</p>
      <p v-else-if="stale" role="status" class="config-hint">配置已修改，请重新测试</p>
      <UiFeedback v-else-if="test?.error">{{ test.error }}</UiFeedback>
      <p v-else-if="test?.result" role="status" class="config-test-success">
        文本流通过 · {{ Math.round(test.result.latency_ms) }} ms
      </p>
      <p class="config-test-caption">仅验证本次文本流，未验证工具能力。</p>
    </div>
    <slot />
  </article>
</template>
