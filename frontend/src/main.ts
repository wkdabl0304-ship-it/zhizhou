/**
 * 浏览器应用入口：创建 Vue 实例，注册全局状态和路由，再挂载到 HTML 容器。
 * 装配聊天原型与开发预览所需的基础设施；尚未发起后端 API 请求。
 */
import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import './styles/base.css'

const app = createApp(App)

// 在挂载前安装插件，确保所有组件都能访问 Pinia 与 Router。
app.use(createPinia())
app.use(router)

// 容器由 frontend/index.html 提供，Vue 接管其内部的页面渲染。
app.mount('#app')
