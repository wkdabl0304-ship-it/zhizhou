# 知舟前端

使用 Vue 3、TypeScript 和 Vite 构建，已接入 Vue Router 与 Pinia。当前页面为初始示例，路由表为空，保留了示例计数器状态和组件测试；尚未实现对话、文件操作或后端 API 接入。

项目定位和功能规划见[根 README](../README.md)。

## 环境与依赖

- Node.js 版本满足 `package.json` 的 `engines.node`：`^22.18.0 || >=24.12.0`。
- 使用 pnpm 管理依赖，仓库已有 `pnpm-lock.yaml`。

在 `frontend/` 目录执行以下命令：

```powershell
pnpm install --frozen-lockfile
pnpm dev
```

开发服务器的访问地址以终端输出为准。当前 `vite.config.ts` 未配置后端代理，项目也未定义后端连接所需的环境变量。

## 构建与检查

| 命令 | 用途 |
| --- | --- |
| `pnpm build` | 执行类型检查并构建，产物输出到 `dist/` |
| `pnpm preview` | 在构建后本地预览产物 |
| `pnpm type-check` | 单独执行 Vue 与 TypeScript 类型检查 |
| `pnpm test:unit` | 使用 Vitest 运行单元测试，默认进入监听模式 |
| `pnpm test:unit --run` | 执行一次单元测试并退出 |
| `pnpm lint` | 依次运行 Oxlint 和 ESLint，脚本会自动修复文件 |
| `pnpm format` | 使用 Prettier 格式化 `src/`，会修改文件 |

单元测试使用 jsdom 环境，当前测试验证初始页面的示例文字。`pnpm preview` 用于本地验证构建产物。

## 目录职责

- `src/main.ts`：创建应用，注册 Pinia 和路由。
- `src/App.vue`：根组件，目前显示初始示例页面。
- `src/router/`：路由配置，目前未定义业务路由。
- `src/stores/`：状态管理，目前包含示例计数器。
- `src/__tests__/`：组件单元测试。
- `public/`：无需构建转换的静态资源。
- `vite.config.ts`：构建与开发服务器配置，`@` 别名指向 `src/`。
- `vitest.config.ts`：单元测试配置。

提交依赖清单和 `pnpm-lock.yaml`；`node_modules/`、`dist/`、覆盖率输出和本地缓存按本目录 `.gitignore` 排除。
