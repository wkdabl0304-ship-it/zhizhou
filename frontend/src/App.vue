<!-- 应用根组件：恢复主题、提供提示上下文，并协调登录结束后的路由回退。 -->
<script setup lang="ts">
import { TooltipProvider } from 'reka-ui'
import { watch } from 'vue'
import { useRouter } from 'vue-router'
import { useThemeStore } from '@/shared/stores/theme'
import { useAuthStore } from '@/features/auth/store'

useThemeStore().initialize()
const auth = useAuthStore()
const router = useRouter()

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
  <!-- 以顶层路由区分页面，聊天/管理子路由切换时保留工作区外壳和侧栏状态。 -->
  <TooltipProvider :delay-duration="350"
    ><RouterView v-slot="{ Component, route }"
      ><component :is="Component" :key="route.matched[0]?.name ?? route.path" /></RouterView
  ></TooltipProvider>
</template>
