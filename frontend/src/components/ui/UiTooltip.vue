<!-- 提示包装：使用 Reka 管理焦点、悬停和定位；允许指定 Portal 容器以支持局部主题。 -->
<script setup lang="ts">
import { computed } from 'vue'
import {
  TooltipContent,
  TooltipPortal,
  TooltipRoot,
  TooltipTrigger,
  useForwardPropsEmits,
  type TooltipRootProps,
  type TooltipRootEmits,
  type TooltipContentProps,
  type TooltipPortalProps,
} from 'reka-ui'

const props = defineProps<
  TooltipRootProps & {
    text: string
    contentProps?: TooltipContentProps
    portalProps?: TooltipPortalProps
  }
>()
const emit = defineEmits<TooltipRootEmits>()
// 只向 Root 转发其自身属性，避免文本等包装层参数污染 DOM。
const rootProps = computed(() => ({
  open: props.open,
  defaultOpen: props.defaultOpen,
  delayDuration: props.delayDuration,
  disabled: props.disabled,
  disableHoverableContent: props.disableHoverableContent,
  ignoreNonKeyboardFocus: props.ignoreNonKeyboardFocus,
  disableClosingTrigger: props.disableClosingTrigger,
}))
const forwarded = useForwardPropsEmits(rootProps, emit)
</script>

<template>
  <TooltipRoot v-bind="forwarded">
    <TooltipTrigger as-child><slot /></TooltipTrigger>
    <TooltipPortal v-bind="portalProps">
      <TooltipContent class="ui-tooltip" :side-offset="8" v-bind="contentProps"
        ><slot name="content">{{ text }}</slot></TooltipContent
      >
    </TooltipPortal>
  </TooltipRoot>
</template>
