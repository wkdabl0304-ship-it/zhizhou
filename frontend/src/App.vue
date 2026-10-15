<!-- 应用根组件：恢复主题，提供统一提示延迟，并通过路由装配聊天与开发预览页面。 -->
<script setup lang="ts">
import { TooltipProvider } from 'reka-ui'
import { useThemeStore } from '@/stores/theme'

useThemeStore().initialize()
</script>

<template>
  <TooltipProvider :delay-duration="350"><RouterView /></TooltipProvider>
</template>
