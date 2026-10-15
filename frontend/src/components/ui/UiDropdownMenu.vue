<!-- 菜单骨架：统一 Portal、定位和外观，菜单项由使用方通过插槽组合 Reka 组件。 -->
<script setup lang="ts">
import { computed } from 'vue'
import {
  DropdownMenuRoot,
  DropdownMenuTrigger,
  DropdownMenuPortal,
  DropdownMenuContent,
  useForwardPropsEmits,
  type DropdownMenuRootProps,
  type DropdownMenuRootEmits,
  type DropdownMenuContentProps,
} from 'reka-ui'

const props = defineProps<DropdownMenuRootProps & { contentProps?: DropdownMenuContentProps }>()
const emit = defineEmits<DropdownMenuRootEmits>()
// 菜单保持 Reka 的受控与非受控约定，页面按需使用 v-model:open。
const rootProps = computed(() => ({
  open: props.open,
  defaultOpen: props.defaultOpen,
  modal: props.modal,
  dir: props.dir,
}))
const forwarded = useForwardPropsEmits(rootProps, emit)
</script>

<template>
  <DropdownMenuRoot v-bind="forwarded">
    <DropdownMenuTrigger as-child><slot name="trigger" /></DropdownMenuTrigger>
    <DropdownMenuPortal>
      <DropdownMenuContent
        class="ui-menu"
        :side-offset="8"
        :collision-padding="12"
        v-bind="contentProps"
        ><slot
      /></DropdownMenuContent>
    </DropdownMenuPortal>
  </DropdownMenuRoot>
</template>
