/**
 * 前端路由集中定义入口，由 main.ts 安装到 Vue 应用。
 * 业务原型使用首页路径，开发预览使用独立懒加载路由，生产构建不注册该入口。
 */
import { createRouter, createWebHistory } from 'vue-router'
import ChatView from '@/views/ChatView.vue'

const router = createRouter({
  // 使用 Vite 的部署基础路径，兼容将来部署在站点子路径的情况。
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'chat', component: ChatView },
    // 编译时常量使生产包移除开发预览模块，而非仅隐藏导航链接。
    ...(import.meta.env.DEV
      ? [
          {
            path: '/dev/ui',
            name: 'components',
            component: () => import('@/views/ComponentPreview.vue'), // 懒加载
          },
        ]
      : []),
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('@/views/NotFoundView.vue'), // 懒加载
    },
  ],
})

export default router
