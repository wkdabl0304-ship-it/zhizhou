/**
 * 前端路由集中定义入口，由 main.ts 安装到 Vue 应用。
 * 当前 routes 为空；新增页面时在这里声明路径与组件的对应关系。
 */
import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  // 使用 Vite 的部署基础路径，兼容将来部署在站点子路径的情况。
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [],
})

export default router
