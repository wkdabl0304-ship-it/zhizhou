/**
 * Vite 开发服务器与生产构建配置，同时作为 Vitest 配置的基础。
 * 当前启用 Vue、开发工具和源码路径别名，尚未配置后端代理。
 */
import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    // 编译 Vue 单文件组件，并在开发环境提供 Vue 调试工具。
    vue(),
    vueDevTools(),
  ],
  resolve: {
    alias: {
      // 通过当前配置文件的 URL 定位 src，避免依赖命令执行时的工作目录。
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
})
