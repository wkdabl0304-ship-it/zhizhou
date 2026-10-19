# 知舟前端

使用 Vue 3、TypeScript 和 Vite 构建，使用 Vue Router 与 Pinia 组织页面和状态，使用 Reka UI 提供交互原语、Lucide Vue 提供线性图标。当前已采用青蓝水墨品牌方案，包含统一舟形 Logo、山海首页、明暗主题和公共组件，聊天页面已实现基础 SSE 回复展示，后端新增思考和工具事件尚待适配；尚未实现文件操作或知识库。

项目定位和功能规划见[根 README](../README.md)。

## 环境与依赖

- Node.js 版本满足 `package.json` 的 `engines.node`：`^22.18.0 || >=24.12.0`。
- 使用 pnpm 管理依赖，仓库已有 `pnpm-lock.yaml`。

在 `frontend/` 目录执行以下命令：

```powershell
pnpm install --frozen-lockfile
pnpm dev
```

开发服务器的访问地址以终端输出为准。先按[后端开发说明](../backend/README.md#启动与聊天接口)准备配置、数据库并启动服务；Vite 开发服务器将 `/api` 请求代理到 `http://127.0.0.1:8000`，保留路径前缀。修改后端端口时同步调整 `vite.config.ts` 的代理目标并重启前端开发服务器。前端未配置模型密钥或其他后端凭据。

生产构建使用同源 `/api/chat`，需要部署端将 `/api` 转发到后端，并关闭 SSE 响应缓冲以便实时交付增量；Vite 开发代理不包含在静态产物中，`pnpm preview` 也不提供此代理。

## 页面与聊天边界

- `/`：聊天工作空间，包含建议问题、本页会话切换、流式聊天、消息复制与自适应输入区。桌面侧栏可以收起，760px 及以下使用模态抽屉。
- `/dev/ui`：仅在 `pnpm dev` 中注册的组件预览页，展示按钮、提示、菜单、抽屉、长文本、等待、失败与禁用状态。生产构建不包含预览页面模块，访问此路径显示未找到页面。
- 其他路径：显示未找到页面，提供返回首页入口。Web History 部署时需要将未知文件路径回退到 `index.html`，由前端路由识别页面。

页面加载时在前端随机生成临时 `thread_id`，首次发送时创建侧栏会话；同一会话的多轮请求复用该标识。点击新建对话会生成另一标识，切换本页已有会话则沿用各自标识。刷新或另开页面会生成新标识，前端不持久化标识、正文，也不恢复后端历史；后端仍按其 checkpoint 机制保存对话。这是为了跑通前后端的临时方案，会话管理未来需要重构。

**当前兼容状态：** 后端已新增 `reasoning_delta / tool_call / tool_start / tool_end / tool_error`。本次仅扩展后端，前端仍严格校验基础事件，收到新事件会显示协议错误，尚不能展示完整执行过程。后续需更新事件解析与过程 UI，并区分单次工具失败和整轮失败；详细字段只维护在[后端说明](../backend/README.md#启动与聊天接口)。以下描述的是现有基础回复客户端的能力。

发送使用 `POST /api/chat`，请求体仍为 `{ message, thread_id }`，通过 fetch 响应流消费 `start / delta / done / error`。适配层处理 UTF-8 和事件跨网络块的拆分，检查 HTTP 状态、SSE 类型、业务码、事件顺序和会话标识；收到终止事件后取消读取并释放流。详细协议只维护在[后端说明](../backend/README.md#启动与聊天接口)。

等待首段时显示等待状态，增量按 `message_id` 分别累积为文本块并实时展示；工具调用前后的助手消息不会拼成同一段。只有 `done` 才确认完成，并以 `done.reply` 替换临时正文，随后允许复制回复。同一会话生成期间可编辑下一条草稿，但不能重复发送；切换会话不影响原请求的回复归属。

网络、HTTP、流内错误或协议异常均显示失败提示；流在 `done` 前结束也视为未完成。已接收的文本、用户消息和当前草稿会保留，不自动重试或续传。切换会话或新建时清空未发送草稿。正式页面不加载演示会话；开发预览仍使用样例。

助手正文通过 `markdown-it` 渲染 Markdown，支持标题、加粗、斜体、删除线、有序与无序列表、引用、表格、链接、图片、分隔线、行内代码和代码块。流式生成时按当前累积源文重新解析，暂未闭合的标记随后续增量更新；用户输入保持纯文本。原始 HTML 标签转义为文本，危险链接协议由解析器过滤；新页链接设置 `noopener noreferrer`。表格与代码块独立横向滚动，适配明暗主题和窄屏。

代码块通过 `highlight.js` 对 JavaScript、TypeScript、Python、JSON、Bash、CSS、HTML/XML、SQL、Markdown 和 YAML 及其别名高亮，未知语言按纯文本展示。代码块可单独复制，不包含高亮标签；整条回复复制保留原始 Markdown。当前未添加数学公式或 Mermaid 图表扩展。`/dev/ui` 提供完整富文本样例，便于检查排版。

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

单元测试使用 jsdom 环境、fetch 替身和真实 ReadableStream，覆盖 SSE 拆包、UTF-8、多行 data、事件顺序及终止校验、读取清理、增量提前展示、最终回答替换、部分输出后失败、临时标识与多轮复用、会话隔离、防重复发送和异步回复归属，以及主题恢复、输入法规则、Markdown 排版与流式重渲染、HTML 和危险链接过滤、代码高亮与复制、复制失败提示和首页发送后的焦点恢复。不连接真实后端、模型或系统剪贴板。`pnpm preview` 用于本地验证生产构建，开发组件预览页在此模式下不可用。

浏览器验收建议检查 1440px、1024px、390px 下的明暗主题、长文本与代码块；验证 Tab/方向键导航、Esc 关闭、焦点恢复、窄屏抽屉背景滚动约束，以及打开抽屉后切回桌面能释放模态状态。代码检查若不希望自动修复，可分别运行 `pnpm exec oxlint .` 与 `pnpm exec eslint .`。

## 目录职责

- `src/main.ts`、`src/App.vue`：应用装配、公共样式、主题初始化及 TooltipProvider。
- `src/router/`、`src/views/`：聊天页面、开发预览与未知路径页面。
- `src/styles/`、`src/components/ui/`：设计变量、基础样式与通用交互组件。
- `src/components/chat/`：侧栏、会话条目、消息与输入区等聊天组件。
- `src/stores/`：内存会话与主题偏好。
- `src/api/`：后端聊天请求、SSE 增量解码和事件校验。
- `src/utils/markdown.ts`：Markdown 安全选项、代码高亮与受控 HTML 渲染；`MarkdownContent.vue` 负责展示样式和代码复制。
- `src/types/`、`src/data/`：聊天展示数据契约、首页建议与开发预览可用的演示数据。
- `src/composables/`：媒体查询等可清理的浏览器响应式逻辑。
- `src/__tests__/`：状态与组件交互回归测试。
- `public/`：站点图标等无需构建转换的静态资源。
- `vite.config.ts`：构建与开发服务器配置，`@` 别名指向 `src/`。
- `vitest.config.ts`：单元测试配置。

提交依赖清单和 `pnpm-lock.yaml`；`node_modules/`、`dist/`、覆盖率输出和本地缓存按[根目录 `.gitignore`](../.gitignore) 的前端规则排除。
