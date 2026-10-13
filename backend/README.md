# 知舟后端

使用 Python 3.14 及以上版本和 uv 管理后端项目。当前已实现最小 FastAPI 聊天接口和可独立运行的智能体示例，通过 LangChain 调用 DeepSeek 的 `deepseek-flash` 模型，并使用 PostgreSQL 保存对话状态。天气工具返回固定演示内容，不连接真实天气服务。

项目定位和功能规划见[根 README](../README.md)。

## 开发命令

在 `backend/` 目录执行：

```powershell
uv sync
uv add <包名>
uv add --dev <包名>
uv run pytest -q
uv build
```

使用 `uv run <命令>` 在项目虚拟环境中执行命令。提交 `pyproject.toml`、`uv.lock` 和 `.python-version`；不提交 `.venv/`、本地环境变量及构建产物。

## 配置与数据库

在仓库根目录准备开发配置并启动数据库：

```powershell
Copy-Item .env.example .env
docker compose -f docker-compose-dev.yml up -d postgres
```

仅在根目录 `.env` 尚不存在时复制，已有配置应直接编辑。Compose 和后端默认共用仓库根目录 `.env`；后端在启动服务或运行示例时显式读取，系统环境变量优先于文件。配置加载不会修改进程环境，也不依赖命令的当前工作目录。

配置项见[环境变量示例](../.env.example)：

- `DEEPSEEK_API_KEY`：在根目录 `.env` 中填写实际 API 密钥；示例文件留空。
- `POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB`：数据库连接参数；示例提供本地开发用值。若通过系统环境变量覆盖，确保与数据库启动配置一致。
- `POSTGRES_PORT`：智能体连接的宿主机端口。Compose 当前固定映射 `5432:5432`，修改此变量时还需要相应修改 Compose 端口映射。

以上配置项均必填且不能仅包含空白；端口必须为 1–65535 之间的整数。当前数据库主机为 `127.0.0.1`，模型地址为 `https://api.deepseek.com`；默认值定义在 `app/config/settings.py`。

配置无效或数据库无法连接时，服务启动失败。服务启动时创建或迁移 checkpoint 表，复用已有对话记录，关闭时释放数据库连接。数据库密码等连接参数由 psycopg 转义，支持特殊字符。

## 启动与聊天接口

安装依赖、填写有效模型密钥并确保数据库可连接后，在 `backend/` 目录运行：

```powershell
uv sync
uv run uvicorn app.main:app --reload
```

打开 [Swagger UI](http://127.0.0.1:8000/docs)，调用 `POST /chat`。请求示例：

```json
{
  "message": "刚刚聊了什么",
  "thread_id": "conversation-001"
}
```

响应包含最终助手回复和原对话标识：

```json
{
  "reply": "模型回复文本",
  "thread_id": "conversation-001"
}
```

`message` 和 `thread_id` 均为必填字符串，空字符串或仅包含空白的字段返回 `422`。相同 `thread_id` 继续已有对话，不同标识隔离历史；服务重启后仍可继续持久化的对话。Agent 执行失败返回通用 `500` 错误，具体异常记录在服务端。

接口为非流式同步调用，FastAPI 在线程池中执行。当前 MVP 通过进程内锁串行执行完整 Agent 调用（不同对话也会排队），请使用单进程运行。尚未提供用户认证、对话所有权校验或生产并发方案；对话标识仅用于区分历史记录。

## 命令行智能体示例

在 `backend/` 目录运行：

```powershell
uv run python -m app.agents
```

编辑 `app/agents/__main__.py` 中的 `MESSAGE` 和 `THREAD_ID` 后即可运行并打印回复。当前默认使用 `conversation-002` 和“刚刚说什么了”；重复运行沿用同一段对话状态，也可与 HTTP 接口共用对话记录。原命令 `uv run python -m app.agents.agent` 仍可使用。

命令行和 HTTP 共用配置、数据库管理和 Agent 实现。导入模块不会加载配置、连接数据库或发起模型调用。

## 测试

```powershell
uv run pytest -q
```

默认测试使用模型及数据库替身和内存 checkpoint，无需真实密钥或 PostgreSQL。覆盖配置校验与优先级、特殊字符连接参数、资源释放、接口校验与错误响应、导入无外部副作用，以及真实 LangChain 图的多轮对话、记录隔离和天气工具调用。

真实服务验证可通过 `/docs` 依次测试：同一 `thread_id` 告知姓名并追问姓名、更换标识确认无之前的历史、重启服务后使用原标识继续对话。测试模型的实际回复不应作为固定文本断言。

## 目录职责

- `app/main.py`：FastAPI 应用、启动/退出资源管理和最小聊天路由。
- `app/agents/`：Agent 专属实现；`models.py` 创建模型，`prompts.py` 定义提示词，`tools/` 定义工具，`factory.py` 组装 Agent，`agent.py` 执行对话，`__main__.py` 提供命令行示例。
- `app/config/`：通用配置加载与校验。
- `app/db/`：数据库资源管理，当前包含 PostgreSQL checkpoint 连接和初始化。
- `app/schemas/`：聊天请求和响应的数据结构。
- `app/api/`、`app/models/`、`app/repositories/`、`app/services/`、`app/utils/`：分别预留给接口模块、业务数据库模型、数据访问、业务服务和通用辅助函数，当前仍为包占位。
- `tests/`：配置、数据库生命周期、Agent 和聊天接口测试。

后续开发外部服务接入时，再按需添加 `app/integrations/`。

接口和智能体工具应复用业务服务，由服务执行文件访问与知识检索的权限校验。

项目使用平铺的 `app/` 包布局，已在 `pyproject.toml` 中显式配置 uv 的包发现路径。
