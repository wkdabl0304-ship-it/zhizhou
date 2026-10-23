/** E2E 专用预览代理：正式静态产物访问本次临时后端，不改变生产部署配置。 */
import { fileURLToPath } from 'node:url'
import { mergeConfig, defineConfig } from 'vite'
import viteConfig from '../../../vite.config'

if (!process.env.E2E_API_URL) throw new Error('请通过 pnpm test:e2e 启动隔离环境')

export default mergeConfig(
  viteConfig,
  defineConfig({
    root: fileURLToPath(new URL('../../../', import.meta.url)),
    preview: { proxy: { '/api': { target: process.env.E2E_API_URL, changeOrigin: true } } },
  }),
)
