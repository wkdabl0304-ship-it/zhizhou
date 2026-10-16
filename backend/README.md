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
uv run python -m app --reload
```

统一启动入口会先加载日志配置，再启动 Uvicorn，默认监听 `127.0.0.1:8000`。可以通过参数修改地址和端口：

```powershell
uv run python -m app --reload --host 0.0.0.0 --port 8080
```

`--reload` 仅用于开发。原命令 `uv run uvicorn app.main:app --reload` 仍可使用，日志会在应用生命周期开始时统一；该兼容方式最早几条 Uvicorn 日志仍使用默认样式。

打开 [Swagger UI](http://127.0.0.1:8000/docs)，在“聊天”分组调用 `POST /api/chat`。请求示例：

```json
{
  "message": "刚刚聊了什么",
  "thread_id": "conversation-001"
}
```

成功响应使用统一格式，`data` 包含最终助手回复和原对话标识：

```json
{
  "code": 0,
  "message": "成功",
  "data": {
    "reply": "模型回复文本",
    "thread_id": "conversation-001"
  }
}
```

请求中的 `message` 和 `thread_id` 均为必填字符串，空字符串、仅包含空白的字段或非法 JSON 返回 HTTP `422` 和统一错误响应。相同 `thread_id` 继续已有对话，不同标识隔离历史；服务重启后仍可继续持久化的对话。Agent 系统失败返回 HTTP `500`，具体异常记录在服务端。

接口为非流式同步调用，FastAPI 在线程池中执行。当前 MVP 通过进程内锁串行执行完整 Agent 调用（不同对话也会排队），请使用单进程运行。尚未提供用户认证、对话所有权校验或生产并发方案；对话标识仅用于区分历史记录。

## 分级 API 路由

普通业务接口统一挂载在 `/api` 下。聊天接口已迁移为 `POST /api/chat`，旧 `POST /chat` 已移除，访问时返回统一 `404` 响应。`/docs` 和 `/openapi.json` 仍保留原地址，不添加业务前缀。

```text
app/
├── main.py                  # 创建应用、管理生命周期、挂载 API 总路由
└── api/
    ├── router.py            # 总路由：声明 /api，集中注册业务子路由
    ├── dependencies.py      # 公共依赖：取得已初始化的 ChatAgent
    ├── exception_handlers.py
    └── routes/
        ├── __init__.py
        └── chat.py          # 聊天子路由：声明 /chat，提供 POST 接口
```

[总路由](app/api/router.py)通过 `include_router` 注册[聊天子路由](app/api/routes/chat.py)，再由应用入口统一挂载。聊天模块的前缀为 `/chat`，POST 使用空相对路径，最终组合为无末尾斜杠的 `/api/chat`。统一异常处理器和公共错误响应文档在应用层注册，自动覆盖子路由。

新增业务模块时：

1. 在 `app/api/routes/` 新建路由模块，使用独立的 `APIRouter` 声明业务前缀、接口和文档分组；不要在子模块重复声明 `/api`。
2. 在 `app/api/router.py` 导入并注册该子路由，无需在 `main.py` 逐个挂载。业务规模扩大后，可在业务模块内继续通过 `include_router` 分级。
3. 通过 `app/api/dependencies.py` 中的公共依赖取得应用资源。聊天接口使用 `Depends(get_chat_agent)` 复用生命周期中的 Agent，不在请求期间创建模型或数据库连接；测试可通过 `app.dependency_overrides` 替换该依赖。

路由和依赖模块不反向导入 `main.py`，避免循环依赖；模块导入不会读取配置、连接数据库或调用模型。

## 统一响应与错误管理

普通 JSON 业务接口统一返回 `code / message / data`，其中 `code` 是整数。成功响应由 `app/schemas/response.py` 的 `success(data)` 构建；路由声明 `ApiResponse[具体数据模型]`，使 OpenAPI 保留成功数据类型。错误由 `app/api/exception_handlers.py` 集中处理，不在每个接口编写兜底 `try/except`。

| 情况 | HTTP 状态 | 响应规则 |
| --- | --- | --- |
| 成功 | 200 | `code=0`，`data` 为业务数据 |
| 明确的业务失败 | 200 | 使用已定义的业务码，`data=null` |
| 参数或协议错误 | 保留对应 4xx | 使用请求错误码，`data=null` |
| 已知系统失败 | 500 | 使用对应系统错误码，`data=null` |
| 其他明确的 HTTP 服务错误 | 保留对应 5xx | 使用通用系统错误码，`data=null` |
| 未知异常或响应模型校验失败 | 500 | 使用通用系统错误码，`data=null` |

HTTP `200` 包含成功和业务失败，调用方必须以 `code === 0` 判断业务成功。所有失败响应只有安全的错误解释，不回传原始请求内容、内部校验详情或异常堆栈。业务失败示例：

```json
{
  "code": 20000,
  "message": "业务处理失败",
  "data": null
}
```

错误码名称、数字及默认解释的唯一维护位置是[错误码目录](app/errors/codes.py)。业务码使用 `20000–29999`，新增真实功能时在该目录业务分组中添加唯一条目，再从业务逻辑抛出 `BusinessError`：

```python
from app.errors.codes import ErrorCode
from app.errors.exceptions import BusinessError

raise BusinessError(ErrorCode.BUSINESS_ERROR)
```

代码通过目录名称引用错误，不散落码值或自定义客户端解释。`BusinessError` 只接受已定义的业务码；`ServiceError` 接受已定义的系统码。异常定义不依赖 FastAPI，供 Agent、业务模块和命令行共用。当前只提供通用业务异常入口，尚未新增额度、权限等具体业务限制。

异常对象的 `error_code` 属性保存 `ErrorCode` 目录成员，可通过 `exc.error_code.code` 和 `exc.error_code.message` 读取数字码与解释；被包装的底层异常通过 `exc.__cause__` 查看。

参数校验统一使用 HTTP `422`；框架级 `404`、`405` 也返回统一格式，必要的 `Allow`、`WWW-Authenticate`、`Retry-After` 等响应头保留。其他 4xx 使用通用请求错误码。普通 `ValueError` 不会被当作业务失败：Agent 的模型调用失败、空回复等转为已知系统异常并保留原始异常链。

业务异常记录 `WARNING`，不输出堆栈；已知系统异常记录 `ERROR` 和堆栈。应用异常携带内部“已记录”标识，避免跨层重复记录。未知异常由全局处理器返回安全响应，Starlette 重抛后由 Uvicorn 记录原始堆栈。应用启动失败仍终止启动，不转换为业务响应。

该约定用于普通 JSON 业务接口；`/docs`、`/openapi.json`、文件下载和未来流式接口保持各自协议，不通过中间件读取并重写响应体。接口文档展示统一模型，并提供 HTTP `200` 下成功和业务失败的示例。

## 命令行智能体示例

在 `backend/` 目录运行：

```powershell
uv run python -m app.agents
```

编辑 `app/agents/__main__.py` 中的 `MESSAGE` 和 `THREAD_ID` 后即可运行并打印回复。当前默认使用 `conversation-002` 和“刚刚说什么了”；重复运行沿用同一段对话状态，也可与 HTTP 接口共用对话记录。原命令 `uv run python -m app.agents.agent` 仍可使用。

命令行和 HTTP 共用配置、数据库管理和 Agent 实现。命令行成功时输出纯文本回复，预期的业务或系统失败以退出码 `1` 结束，已记录的异常不会再次由解释器打印堆栈。导入模块不会加载配置、连接数据库或发起模型调用。

## 统一日志

项目统一使用 Python 标准库 `logging`。配置位于 `app/config/logging.py`，环境读取与校验位于 `app/config/settings.py`；Web 启动入口、应用生命周期和智能体命令行入口显式初始化，导入模块不配置全局日志。

以下配置项均可选，读取仓库根目录 `.env`，系统环境变量优先。未配置时使用默认值；修改后需重启启动入口。

| 环境变量 | 默认值 | 用途 |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | 应用与 Uvicorn 日志级别 |
| `LOG_THIRD_PARTY_LEVEL` | `WARNING` | 第三方库日志级别 |
| `LOG_ACCESS_ENABLED` | `true` | 是否输出 Uvicorn HTTP 访问日志 |

级别支持 `DEBUG`、`INFO`、`WARNING`、`ERROR`、`CRITICAL`，忽略大小写；访问日志开关支持 `true/false` 和 `1/0`，忽略大小写。显式空值或非法值使启动失败，并指出配置项。日志配置加载不依赖模型密钥或数据库配置，因此业务初始化失败也能记录异常。

日志采用统一文本格式，包含本地时间、级别、模块名和消息，输出到 `stderr`；命令行最终回复仍输出到 `stdout`。重复初始化不会叠加 handler，应用、Uvicorn 和第三方日志均经统一控制台 handler 输出。

```text
2026-10-13 15:30:02 INFO app.main 应用启动完成
2026-10-13 15:30:04 INFO app.agents.agent 对话完成 thread_id='conversation-001' duration_ms=1820.00
```

应用记录启动完成、启动失败和资源关闭。Agent 记录对话成功或失败、对话标识和耗时，计时包含等待对话锁的排队时间；业务失败无堆栈，系统失败保留堆栈。已知应用异常按“已记录”标识避免重复输出，未知异常由 Uvicorn 记录。默认不主动记录聊天正文、模型回复、密钥或数据库连接串。本阶段不提供请求 ID、日志文件或第三方日志库。

各模块使用标准 logger，只记录自身事件，不添加 handler 或重新初始化日志：

```python
import logging

logger = logging.getLogger(__name__)
logger.info("业务事件")
```

集中配置会保留第三方 logger 的启用状态，并统一控制应用、Uvicorn 与第三方日志的输出级别。容器部署时由运行环境收集控制台日志。

## 测试

```powershell
uv run pytest -q
```

默认测试使用模型及数据库替身和内存 checkpoint，无需真实密钥或 PostgreSQL。覆盖配置校验与优先级、特殊字符连接参数、资源释放、接口校验与错误响应、导入无外部副作用，以及真实 LangChain 图的多轮对话、记录隔离和天气工具调用。日志测试额外覆盖级别、访问日志开关、重复初始化、Uvicorn 子进程配置、启动参数以及对话日志的耗时与异常；全局日志配置在独立子进程中验证，保留其他测试的日志捕获能力。

路由测试验证 `/api/chat` 的请求与响应、旧路径 `404`、错误方法 `405` 及 `Allow` 头、Agent 实例复用、依赖覆盖和 OpenAPI 路径、分组与响应示例。

错误处理测试覆盖码值唯一性、业务码类型与范围、成功数据类型、业务失败 HTTP `200`、参数与协议错误、响应头保留、未知异常与响应模型校验失败，以及 CLI 退出码和异常日志不重复。另用短暂启动的本地 Uvicorn 服务验证兜底响应和实际堆栈输出，测试完成即关闭服务；该测试也不依赖模型或数据库。

真实服务验证可通过 `/docs` 依次测试：同一 `thread_id` 告知姓名并追问姓名、更换标识确认无之前的历史、重启服务后使用原标识继续对话。测试模型的实际回复不应作为固定文本断言。

## 目录职责

- `app/__main__.py`：统一 Web 启动入口，处理地址、端口、reload 参数并向 Uvicorn 传递日志配置。
- `app/main.py`：FastAPI 应用、启动/退出资源管理、全局异常处理器注册和 API 总路由挂载。
- `app/agents/`：Agent 专属实现；`models.py` 创建模型，`prompts.py` 定义提示词，`tools/` 定义工具，`factory.py` 组装 Agent，`agent.py` 执行对话，`__main__.py` 提供命令行示例。
- `app/config/`：通用配置加载与校验，以及标准 logging 集中配置。
- `app/db/`：数据库资源管理，当前包含 PostgreSQL checkpoint 连接和初始化。
- `app/errors/`：错误码与默认解释、应用异常类型和异常日志责任。
- `app/schemas/`：聊天请求、聊天数据模型及通用响应模型和构建函数。
- `app/api/`：API 总路由、公共请求依赖、按业务划分的子路由，以及统一异常处理器和错误响应文档；结构与扩展步骤见[分级 API 路由](#分级-api-路由)。
- `app/models/`、`app/repositories/`、`app/services/`、`app/utils/`：分别预留给业务数据库模型、数据访问、业务服务和通用辅助函数，当前仍为包占位。
- `tests/`：配置、数据库生命周期、Agent 和聊天接口测试。

后续开发外部服务接入时，再按需添加 `app/integrations/`。

接口和智能体工具应复用业务服务，由服务执行文件访问与知识检索的权限校验。

项目使用平铺的 `app/` 包布局，已在 `pyproject.toml` 中显式配置 uv 的包发现路径。
