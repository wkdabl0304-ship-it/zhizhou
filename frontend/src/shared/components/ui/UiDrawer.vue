<!-- 侧栏抽屉：基于模态 Dialog，保留焦点约束、Esc 关闭及关闭后恢复触发器焦点。 -->
<script setup lang="ts">
import { computed } from 'vue'
import { X } from '@lucide/vue'
import {
  DialogRoot,
  DialogTrigger,
  DialogPortal,
  DialogOverlay,
  DialogContent,
  DialogTitle,
  DialogDescription,
  DialogClose,
  useForwardProps,
  type DialogRootProps,
  type DialogRootEmits,
  type DialogContentProps,
  type DialogContentEmits,
} from 'reka-ui'
import UiIconButton from './UiIconButton.vue'
import { useDialogLayer } from '@/shared/composables/useDialogLayer'
const { overlayStyle, contentStyle } = useDialogLayer()

const props = defineProps<
  DialogRootProps & { title: string; description: string; contentProps?: DialogContentProps }
>()
const emit = defineEmits<DialogRootEmits & DialogContentEmits>()
const rootProps = computed(() => ({
  open: props.open,
  defaultOpen: props.defaultOpen,
  modal: props.modal,
  unmountOnHide: props.unmountOnHide,
}))
const forwarded = useForwardProps(rootProps)
</script>

<template>
  <DialogRoot v-bind="forwarded" @update:open="emit('update:open', $event)">
    <DialogTrigger as-child><slot name="trigger" /></DialogTrigger>
    <DialogPortal>
      <DialogOverlay class="ui-drawer-overlay" :style="overlayStyle" />
      <DialogContent
        class="ui-drawer"
        data-ui-dialog
        :style="contentStyle"
        v-bind="contentProps"
        @open-auto-focus="emit('openAutoFocus', $event)"
        @close-auto-focus="emit('closeAutoFocus', $event)"
        @escape-key-down="emit('escapeKeyDown', $event)"
        @pointer-down-outside="emit('pointerDownOutside', $event)"
        @focus-outside="emit('focusOutside', $event)"
        @interact-outside="emit('interactOutside', $event)"
      >
        <DialogTitle class="sr-only">{{ title }}</DialogTitle>
        <DialogDescription class="sr-only">{{ description }}</DialogDescription>
        <slot />
        <DialogClose as-child
          ><UiIconButton class="ui-drawer-close" label="关闭侧栏"><X :size="18" /></UiIconButton
        ></DialogClose>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
