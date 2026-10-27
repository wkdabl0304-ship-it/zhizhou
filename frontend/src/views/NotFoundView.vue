<!-- 未知路径页面：生产环境访问开发预览页时也进入此处，不暴露开发组件入口。 -->
<script setup lang="ts">
import UiPageHeader from '@/shared/components/ui/UiPageHeader.vue'
</script>
<template>
  <main class="not-found">
    <UiPageHeader
      eyebrow="404"
      title="这条航线还没有开通"
      description="回到知舟，开始一段新的对话。"
      align="center"
    />
    <RouterLink to="/">返回首页</RouterLink>
  </main>
</template>
<style scoped>
.not-found {
  padding: 20vh 24px;
  text-align: center;
}
</style>
