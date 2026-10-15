<!-- 图标按钮：强制提供可访问名称，原生属性和事件落到唯一按钮根节点。 -->
<script setup lang="ts">
withDefaults(
  defineProps<{
    label: string
    active?: boolean
    disabled?: boolean
    type?: 'button' | 'submit'
  }>(),
  { type: 'button' },
)
</script>

<template>
  <button
    :type="type"
    class="ui-icon-button"
    :class="{ 'is-active': active }"
    :aria-label="label"
    :disabled="disabled"
  >
    <slot />
  </button>
</template>
