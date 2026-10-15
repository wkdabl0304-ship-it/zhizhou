/**
 * Vitest 单元测试配置：复用 Vite 的插件和别名，再设置模拟浏览器环境。
 * 测试根目录固定为前端目录，排除默认产物和独立端到端测试目录。
 */
import { fileURLToPath } from 'node:url'
import { mergeConfig, defineConfig, configDefaults } from 'vitest/config'
import viteConfig from './vite.config.ts'

export default mergeConfig(
  // 合并配置确保 .vue 测试采用与真实应用一致的组件编译规则。
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      // 追加排除项时保留 Vitest 默认规则，避免把依赖或构建文件当作测试。
      exclude: [...configDefaults.exclude, 'e2e/**'],
      root: fileURLToPath(new URL('./', import.meta.url)),
    },
  }),
)
