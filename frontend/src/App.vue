<!-- 应用根组件：恢复主题、提供提示上下文，并协调身份变化与本页聊天展示的隔离。 -->
<script setup lang="ts">
import { TooltipProvider } from 'reka-ui'
import { watch } from 'vue'
import { useRouter } from 'vue-router'
import { useThemeStore } from '@/stores/theme'
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/features/auth/store'

useThemeStore().initialize()
const auth = useAuthStore()
const chat = useChatStore()
const router = useRouter()

// 账号离开时立即移除界面中的临时聊天；旧请求持有旧对象，不会串写到新账号列表。
watch(
  () => auth.user?.id,
  (identity, previous) => {
    if (previous && previous !== identity) chat.clearLocal()
  },
  { flush: 'sync' },
)

// 定时到期或主动退出也会触发路由回退，不必等用户再次点击导航。
watch(
  () => auth.isAuthenticated,
  (authenticated, previous) => {
    if (previous && !authenticated && router.currentRoute.value.meta.requiresAuth)
      void router.replace({
        name: 'login',
        query: { redirect: router.currentRoute.value.fullPath },
      })
  },
)
</script>

<template>
  <TooltipProvider :delay-duration="350"
    ><RouterView v-slot="{ Component, route }"
      ><component :is="Component" :key="route.name ?? route.path" /></RouterView
  ></TooltipProvider>
</template>
