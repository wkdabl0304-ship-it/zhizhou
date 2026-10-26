<!-- 模型方案卡片：显示目录可用性与版本对应的文本流测试结果，操作通过事件交由页面确认。 -->
<script setup lang="ts">
import { computed } from 'vue'
import UiButton from '@/shared/components/ui/UiButton.vue'
import { describeReasoning } from '../validation'
import type { ModelConfiguration, TestResult } from '../types'
const props = defineProps<{
  model: ModelConfiguration
  providerVersion: number
  current: boolean
  busy: boolean
  test?: { running: boolean; result?: TestResult; error?: string }
}>()
defineEmits<{ test: []; select: []; edit: []; delete: []; toggle: [] }>()
const stale = computed(
  () =>
    !!props.test?.result &&
    (props.test.result.model_version !== props.model.version ||
      props.test.result.provider_configuration_version !== props.providerVersion),
)
</script>
<template>
  <article class="config-model-card" :aria-label="`模型方案：${model.name}`">
    <div class="config-section-heading">
      <h3>{{ model.name }}</h3>
      <div class="config-actions">
        <span v-if="current" class="config-badge">当前默认</span
        ><span v-if="!model.available" class="config-badge config-badge--invalid">不可用</span>
        <span v-if="!model.enabled" class="config-badge config-badge--invalid">已停用</span>
        <span
          v-else-if="model.available && !model.selectable"
          class="config-badge config-badge--invalid"
          >连接已停用</span
        >
      </div>
    </div>
    <p class="config-model-id">{{ model.catalog?.display_name ?? model.catalog_model_id }}</p>
    <div class="config-model-options">
      <span>{{ model.reasoning_policy.mode === 'fixed' ? '固定推理' : '允许用户自选' }}</span>
      <span>{{ describeReasoning(model.reasoning) }}</span
      ><span>输出上限 · {{ model.max_output_tokens.toLocaleString() }}</span>
    </div>
    <p v-if="!model.available" class="config-error">此模型当前不可用，请编辑方案选择可用模型。</p>
    <div class="config-model-footer">
      <span v-if="test?.running" class="config-hint" role="status">正在测试文本流…</span>
      <span v-else-if="stale" class="config-hint">配置已修改，请重新测试</span>
      <span v-else-if="test?.error" class="config-error" role="status">{{ test.error }}</span>
      <span v-else-if="test?.result" class="config-test-success" role="status"
        >文本流通过 · {{ Math.round(test.result.latency_ms) }} ms</span
      >
      <span v-else class="config-hint">尚未测试</span>
      <div class="config-actions">
        <UiButton
          size="sm"
          :disabled="busy || !model.available"
          :loading="test?.running"
          @click="$emit('test')"
          >测试</UiButton
        ><UiButton
          v-if="!current"
          size="sm"
          :disabled="busy || !model.selectable"
          @click="$emit('select')"
          >设为默认</UiButton
        ><UiButton size="sm" variant="ghost" :disabled="busy" @click="$emit('toggle')">{{
          model.enabled ? '停用' : '启用'
        }}</UiButton
        ><UiButton size="sm" variant="ghost" :disabled="busy" @click="$emit('edit')">编辑</UiButton
        ><UiButton
          size="sm"
          variant="ghost"
          class="config-danger"
          :disabled="busy"
          @click="$emit('delete')"
          >删除</UiButton
        >
      </div>
    </div>
    <p v-if="test?.result && !stale" class="config-test-caption">
      仅验证本次文本流，未验证工具能力。
    </p>
  </article>
</template>
