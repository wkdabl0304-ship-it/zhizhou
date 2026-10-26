/** 真实浏览器测试：由隔离启动器提供后端地址，预览正式产物，失败保留诊断材料。 */
import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  workers: 2,
  retries: 0,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  outputDir: 'test-results/artifacts',
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
  use: {
    baseURL: process.env.E2E_BASE_URL,
    browserName: 'chromium',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    reducedMotion: 'reduce',
  },
  projects: [
    {
      name: 'chromium-desktop',
      testIgnore: '**/model-config.spec.ts',
      use: { viewport: { width: 1440, height: 900 } },
    },
    {
      name: 'chromium-narrow',
      testIgnore: '**/model-config.spec.ts',
      use: { viewport: { width: 390, height: 844 } },
    },
    // 配置由所有账号共享：先完成既有并行流程，再串行运行会清空/切换全局配置的场景。
    {
      name: 'model-config-desktop',
      testMatch: '**/model-config.spec.ts',
      dependencies: ['chromium-desktop', 'chromium-narrow'],
      workers: 1,
      fullyParallel: false,
      use: { viewport: { width: 1440, height: 900 } },
    },
    {
      name: 'model-config-narrow',
      testMatch: '**/model-config.spec.ts',
      dependencies: ['model-config-desktop'],
      workers: 1,
      fullyParallel: false,
      use: { viewport: { width: 390, height: 844 } },
    },
  ],
  webServer: {
    command: `node node_modules/vite/bin/vite.js preview --config tests/support/playwright/vite.config.ts --host 127.0.0.1 --port ${process.env.E2E_WEB_PORT} --strictPort`,
    url: `${process.env.E2E_BASE_URL}/login`,
    reuseExistingServer: false,
    timeout: 30_000,
  },
})
