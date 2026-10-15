<!-- 未知路径页面：生产环境访问开发预览页时也进入此处，不暴露开发组件入口。 -->
<template>
  <main class="not-found">
    <span>404</span>
    <h1>这条航线还没有开通</h1>
    <p>回到知舟，开始一段新的对话。</p>
    <RouterLink to="/">返回首页</RouterLink>
  </main>
</template>
<style scoped>
.not-found {
  padding: 20vh 24px;
  text-align: center;
}
span {
  color: var(--brand);
  font-size: 14px;
}
h1 {
  font-size: 24px;
  font-weight: 500;
}
p {
  color: var(--text-secondary);
}
</style>
