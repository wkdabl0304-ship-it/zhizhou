# 知舟前端

使用 Vue 3、TypeScript 和 Vite 构建，使用 Vue Router 与 Pinia 组织页面和状态，使用 Reka UI 提供交互原语、Lucide Vue 提供线性图标。当前已采用青蓝水墨品牌方案，包含统一舟形 Logo、山海首页、明暗主题、公共组件和可交互的静态聊天原型；尚未接入后端 API、文件操作或知识库。

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

## 页面与演示边界

- `/`：聊天工作空间，包含示例问题、演示会话切换、消息复制与自适应输入区。桌面侧栏可以收起，760px 及以下使用模态抽屉。
- `/dev/ui`：仅在 `pnpm dev` 中注册的组件预览页，展示按钮、提示、菜单、抽屉、长文本、等待、失败与禁用状态。生产构建不包含预览页面模块，访问此路径显示未找到页面。
- 其他路径：显示未找到页面，提供返回首页入口。Web History 部署时需要将未知文件路径回退到 `index.html`，由前端路由识别页面。

所有会话都是虚构演示数据。发送只在当前页面内存中追加消息和带“演示回复”标识的固定文本，不调用后端或模型；刷新会恢复初始会话。切换会话或新建时清空未发送草稿。消息按段落、列表、代码块结构渲染为文本，不解析 HTML，也未实现完整 Markdown。

Enter 发送，Shift+Enter 换行；中文输入法组合输入及确认不会发送。输入框自动增高并在上限后内部滚动，消息滚动区域与底部输入区独立布局。复制回复使用浏览器剪贴板 API，通常要求 HTTPS 或 localhost；失败时显示手动复制提示。

## 公共样式与组件约定

正式界面采用青蓝水墨与“现代宋体”标题，保留文案“心有山海，自有知舟”，通过宋体笔锋、疏朗字距和青蓝强调线呈现品牌。`WelcomeHeading.vue` 承载首页标题，桌面字号上限 74px，窄屏使用 49px；宋体使用本机字体，跨设备字形可能不同，正文仍使用公共无衬线字体。界面使用冷白、深靛与青蓝色彩，并保留侧栏收起、消息复制、主题记忆和窄屏抽屉。`BrandLogo.vue` 与 `RiverBackdrop.vue` 分别导入舟形和水墨素材。`ChatWelcome.vue` 组合首页视觉与真实输入区，不直接依赖会话 store。

首页水墨由 `RiverBackdrop.vue` 铺满整个主区域（含页头），与限宽标题和输入区独立；按容器比例裁切素材，窄屏也不会露出局部插图边框。山景以 14 秒单程周期漂移，双层流雾和水面光带以 7–9 秒单程周期错向移动；标题两行轻微错拍浮动，字形内的青蓝流光与强调水线独立播放，输入区保持稳定。进入对话正文后卸载首页背景和标题。`useMotionPreference` 管理首页动效：系统减少动态效果优先，页面隐藏时暂停动画（含伪元素上的雾带与水线）。页面和弹层统一使用根主题。水墨 PNG 由内置 imagegen 生成，Logo 为原创 SVG；素材与最终提示词见[生成记录](src/assets/brand/generation-notes.md)。基础组件预览页不进入生产包。

- `src/styles/tokens.css` 是设计变量的维护位置，统一颜色、字体、间距、圆角、阴影和层级。默认浅色；深色由根元素的 `data-theme="dark"` 启用。`zhizhou-theme` 是唯一写入 localStorage 的偏好，不保存聊天正文。
- `src/styles/base.css` 定义基础样式及共享 UI 外观。消息、侧栏、输入区等业务组件使用各自局部样式；业务组件引用语义变量，避免散落明暗配色。
- `src/components/ui/` 提供按钮、图标按钮、自适应文本框，以及基于 Reka 的 Tooltip、DropdownMenu 和 Dialog 抽屉。使用方通过 props、事件和插槽组合；触发器使用 `asChild` 复用原生按钮，避免嵌套交互元素。
- 菜单、提示和抽屉内容通过 Portal 挂载，主题变量因此定义在文档根元素；共享弹层类不依赖页面祖先选择器。Reka 管理键盘、焦点及模态行为，包装组件负责外观和必要事件转发。
- 图标从 `@lucide/vue` 按需导入。图标按钮必须有可访问名称；抽屉必须提供标题和描述。动画遵循 `prefers-reduced-motion`。

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

单元测试使用 jsdom 环境，覆盖会话创建与隔离、演示数据重置、主题恢复与存储异常、输入法和发送约束、消息安全渲染、复制失败提示，以及首页发送后的焦点恢复。不连接真实后端、模型或系统剪贴板。`pnpm preview` 用于本地验证生产构建，开发组件预览页在此模式下不可用。

浏览器验收建议检查 1440px、1024px、390px 下的明暗主题、长文本与代码块；验证 Tab/方向键导航、Esc 关闭、焦点恢复、窄屏抽屉背景滚动约束，以及打开抽屉后切回桌面能释放模态状态。代码检查若不希望自动修复，可分别运行 `pnpm exec oxlint .` 与 `pnpm exec eslint .`。

## 目录职责

- `src/main.ts`、`src/App.vue`：应用装配、公共样式、主题初始化及 TooltipProvider。
- `src/router/`、`src/views/`：聊天页面、开发预览与未知路径页面。
- `src/styles/`、`src/components/ui/`：设计变量、基础样式与通用交互组件。
- `src/components/chat/`：侧栏、会话条目、消息与输入区等聊天组件。
- `src/stores/`：内存会话与主题偏好。
- `src/types/`、`src/data/`：前端原型数据契约与独立创建的演示数据；不等同于后端接口模型。
- `src/composables/`：媒体查询等可清理的浏览器响应式逻辑。
- `src/__tests__/`：状态与组件交互回归测试。
- `public/`：站点图标等无需构建转换的静态资源。
- `vite.config.ts`：构建与开发服务器配置，`@` 别名指向 `src/`。
- `vitest.config.ts`：单元测试配置。

提交依赖清单和 `pnpm-lock.yaml`；`node_modules/`、`dist/`、覆盖率输出和本地缓存按[根目录 `.gitignore`](../.gitignore) 的前端规则排除。
