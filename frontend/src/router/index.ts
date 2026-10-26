/**
 * 前端路由集中定义入口，由 main.ts 安装到 Vue 应用。
 * 认证页和聊天工作区使用独立路由；开发预览不要求登录，生产构建不注册该入口。
 */
import { createRouter, createWebHistory, type RouterHistory } from 'vue-router'
import ChatView from '@/views/ChatView.vue'
import WorkspaceLayout from '@/layouts/WorkspaceLayout.vue'
import { useAuthStore } from '@/features/auth/store'
import { postLoginPath } from '@/features/auth/validation'

/** 创建带认证守卫的应用路由；测试可注入内存历史，不修改浏览器地址或共享导航状态。 */
export function createAppRouter(
  history: RouterHistory = createWebHistory(import.meta.env.BASE_URL),
) {
  const router = createRouter({
    // 使用 Vite 的部署基础路径，兼容将来部署在站点子路径的情况。
    history,
    routes: [
      {
        path: '/',
        name: 'workspace',
        component: WorkspaceLayout,
        meta: { requiresAuth: true },
        // 两个业务页面只替换主内容，共用同一个导航实例。
        children: [
          { path: '', name: 'chat', component: ChatView },
          {
            path: 'models',
            name: 'models',
            component: () => import('@/views/ModelManagementView.vue'),
          },
        ],
      },
      {
        path: '/login',
        name: 'login',
        component: () => import('@/views/AuthView.vue'),
        props: { mode: 'login' },
        meta: { guestOnly: true },
      },
      {
        path: '/register',
        name: 'register',
        component: () => import('@/views/AuthView.vue'),
        props: { mode: 'register' },
        meta: { guestOnly: true },
      },
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

  // 所有身份恢复合并到 store；登录路由只接受本应用入口作为返回地址，防止外部跳转。
  router.beforeEach(async (to) => {
    if (!to.meta.requiresAuth && !to.meta.guestOnly) return true
    const auth = useAuthStore()
    await auth.initialize()
    if (to.meta.requiresAuth && !auth.isAuthenticated)
      return { name: 'login', query: { redirect: to.fullPath }, replace: true }
    if (to.meta.guestOnly && auth.isAuthenticated) return postLoginPath(to.query.redirect)
    return true
  })
  return router
}

export default createAppRouter()
