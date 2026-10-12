# 知舟后端

使用 Python 3.14 及以上版本和 uv 管理后端项目，已声明 FastAPI、LangChain、模型调用及 PostgreSQL checkpoint 相关依赖。当前包含目录骨架和独立智能体示例；`app/main.py` 为空，尚未创建 FastAPI 应用，也没有可启动的 API 服务。

项目定位和功能规划见[根 README](../README.md)。

## 开发命令

在 `backend/` 目录执行：

```powershell
uv sync
uv add <包名>
uv add --dev <包名>
uv build
```

使用 `uv run <命令>` 在项目虚拟环境中执行命令。提交 `pyproject.toml`、`uv.lock` 和 `.python-version`；不提交 `.venv/`、本地环境变量及构建产物。

## 数据库与智能体示例

`app/agents/agent.py` 通过 LangChain 调用 DeepSeek 的 `deepseek-flash` 模型，并使用 PostgreSQL 保存对话状态。天气工具返回固定演示内容，不连接真实天气服务。

在仓库根目录准备开发配置并启动数据库：

```powershell
Copy-Item .env.example .env
Copy-Item .env.example backend/.env
docker compose -f docker-compose-dev.yml up -d postgres
```

仅在对应 `.env` 尚不存在时复制，已有配置应直接编辑。根目录 `.env` 供 Compose 使用，`backend/.env` 是当前智能体脚本显式加载的路径，两者不会自动同步。

配置项见[环境变量示例](../.env.example)：

- `DEEPSEEK_API_KEY`：在 `backend/.env` 中填写实际 API 密钥；示例文件留空。
- `POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB`：两份配置应保持一致；示例提供本地开发用值。
- `POSTGRES_PORT`：智能体连接的宿主机端口。Compose 当前固定映射 `5432:5432`，修改此变量时还需要相应修改 Compose 端口映射。

安装依赖并确保数据库可连接后，在 `backend/` 目录运行：

```powershell
uv run python -m app.agents.agent
```

脚本使用 `127.0.0.1` 连接数据库，创建 checkpoint 相关表，以固定的 `conversation-001` 对话标识发送示例消息，再打印回复。重复运行会沿用同一段对话状态。执行或导入该模块都会连接数据库并发起模型调用。

## 目录职责

- `app/main.py`：应用入口，待实现。
- `app/api/`：HTTP 接口。
- `app/agents/`：智能体示例，当前包含模型、工具和 PostgreSQL checkpoint 接入。
- `app/config/`：配置相关代码，当前为包占位。
- `app/db/`：数据库连接和会话。
- `app/models/`：数据库模型。
- `app/schemas/`：请求和响应的数据结构。
- `app/repositories/`：数据库查询和写入。
- `app/services/`：业务流程和规则。
- `app/utils/`：不含业务规则的通用辅助函数。
- `tests/`：后端测试，按功能添加。

后续开发外部服务接入时，再按需添加 `app/integrations/`。

接口和智能体工具应复用业务服务，由服务执行文件访问与知识检索的权限校验。

项目使用平铺的 `app/` 包布局，已在 `pyproject.toml` 中显式配置 uv 的包发现路径。
