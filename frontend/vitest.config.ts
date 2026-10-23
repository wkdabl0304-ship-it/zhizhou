/** Vitest 总配置：模块测试就近维护，应用集成测试集中收集，两者默认一并执行。 */
import { fileURLToPath } from 'node:url'
import { mergeConfig, defineConfig } from 'vitest/config'
import viteConfig from './vite.config.ts'

export default mergeConfig(
  viteConfig,
  defineConfig({
    resolve: { alias: { '@tests': fileURLToPath(new URL('./tests', import.meta.url)) } },
    test: {
      root: fileURLToPath(new URL('./', import.meta.url)),
      coverage: {
        provider: 'v8',
        reporter: ['text', 'html', 'json', 'json-summary'],
        include: ['src/**/*.{ts,vue}'],
        exclude: [
          'src/**/__tests__/**',
          'src/**/*.d.ts',
          'src/dev/**',
          'src/views/ComponentPreview.vue',
        ],
      },
      projects: [
        {
          extends: true,
          test: {
            name: 'modules',
            environment: 'jsdom',
            include: ['src/**/__tests__/**/*.spec.ts', 'tests/support/__tests__/**/*.spec.ts'],
            setupFiles: ['tests/support/vitest/setup.ts'],
          },
        },
        {
          extends: true,
          test: {
            name: 'integration',
            environment: 'jsdom',
            include: ['tests/integration/**/*.spec.ts'],
            setupFiles: ['tests/support/vitest/setup.ts'],
          },
        },
      ],
    },
  }),
)
