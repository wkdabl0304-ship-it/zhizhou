/** 开发预览浏览器配置：独立启动本地 Vite，仅验收开发组件页，不改变生产路由或连接业务后端。 */
import { fileURLToPath } from 'node:url'
import { defineConfig } from '@playwright/test'
import { browserLaunchOptions } from './browser'

export default defineConfig({
  testDir: '../../preview-e2e',
  outputDir: '../../../test-results/control-preview',
  reporter: 'list',
  workers: 1,
  timeout: 30_000,
  use: {
    baseURL: 'http://127.0.0.1:4187',
    browserName: 'chromium',
    launchOptions: browserLaunchOptions(),
    reducedMotion: 'reduce',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'controls-desktop', use: { viewport: { width: 1440, height: 1000 } } },
    { name: 'controls-narrow', use: { viewport: { width: 390, height: 844 } } },
  ],
  webServer: {
    command: 'pnpm exec vite --host 127.0.0.1 --port 4187 --strictPort',
    cwd: fileURLToPath(new URL('../../..', import.meta.url)),
    url: 'http://127.0.0.1:4187/dev/ui',
    reuseExistingServer: false,
    timeout: 30_000,
  },
})
