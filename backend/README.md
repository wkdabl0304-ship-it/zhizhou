# 知舟后端

使用 Python 3.14 及以上版本和 uv 管理后端项目。当前已实现账号密码注册、JWT 登录、用户会话隔离、游标读取最近及更早的会话和历史、软删除，以及异步 SSE 聊天与公开工具过程持久化。业务数据使用 SQLAlchemy 2.1 异步 ORM 与 Alembic，模型上下文由 LangGraph 的 PostgreSQL checkpoint 独立保存。通过 DeepSeek 专用适配调用 `deepseek-flash`，不对外返回模型推理。天气工具返回固定演示内容。

前端本期尚未接入认证和业务会话 ID，不能直接使用新聊天接口；可通过 Swagger 或 HTTP 客户端验收，前端接入要求见下文。

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

默认测试需要已运行的 PostgreSQL，快速单元测试和专项命令见[测试](#测试)。

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
- `POSTGRES_HOST`：默认 `127.0.0.1`，显式提供时不能为空。
- `JWT_SECRET`：必填，至少 32 字节的独立随机密钥，没有默认值；不要填写示例密码或提交到 Git。
- `JWT_TTL_SECONDS`：默认 `7200`，必须为正整数；过期后重新登录，不提供刷新或服务端撤销。

模型密钥、数据库用户、密码、库名、端口及 JWT 密钥必填且不能仅包含空白；端口范围为 1–65535。模型地址为 `https://api.deepseek.com`，默认值定义在 `app/core/settings.py`。可运行 `uv run python -c "import secrets; print(secrets.token_urlsafe(48))"` 生成独立随机 JWT 密钥，再保存到本地 `.env`。

配置无效、业务表未迁移、版本不匹配或数据库无法连接时，服务启动失败。首次启动前在 `backend/` 执行：

```powershell
uv sync
uv run alembic upgrade head
```

Alembic 配置在 `pyproject.toml`，使用异步 Psycopg 引擎，迁移只需要数据库配置，不要求模型或 JWT 密钥。以后修改实体时用 `uv run alembic revision --autogenerate -m "变更说明"` 生成迁移并人工审阅，再执行升级；`uv run alembic check` 检查实体与实际结构是否一致。不要在应用启动时用 `create_all` 代替迁移。

SQLAlchemy 业务引擎和 Session 工厂在生命周期中创建，短事务独立使用 `AsyncSession`，退出时异步释放连接池。`AsyncPostgresSaver` 仍自行初始化和管理 checkpoint 表，Alembic 自动比较明确排除这些第三方表。凭据通过 SQLAlchemy URL 对象或 Psycopg 转义，支持特殊字符，不写入迁移配置。

## 认证与会话接口

所有响应沿用 `{code, message, data}`，成功 `code=0`。除注册和登录外，业务接口要求 `Authorization: Bearer <access_token>`；Swagger 点击 Authorize 后填入登录返回的 JWT 即可。

| 方法与路径 | 输入 | 成功 data |
| --- | --- | --- |
| `POST /api/auth/register` | `{username,password,role?}` | `{id,username,role,created_at}` |
| `POST /api/auth/login` | `{username,password}` | `{access_token,token_type,expires_in,user}` |
| `GET /api/auth/me` | Bearer JWT | `{id,username,role}` |
| `GET /api/conversations` | `limit=20&cursor=...` | `{items,next_cursor}` |
| `GET /api/conversations/{conversation_id}` | `limit=20&cursor=...` | `{conversation,items,next_cursor}` |
| `DELETE /api/conversations/{conversation_id}` | 无请求体 | `null` |
| `POST /api/chat` | `{message,conversation_id?}` | SSE，见下一节 |

注册成功后单独登录。用户名去除首尾空白并转小写，限定 3～32 位 ASCII 字母、数字或下划线；密码 8～128 个字符，不去除空格，使用 Argon2 摘要，哈希与校验在线程池执行。角色仅允许 `user` 和 `super_admin`，默认 `user`；两种角色均只能操作自己的会话，当前没有跨用户管理功能。

JWT 使用 HS256，必需声明为 `sub / iat / exp / iss / aud`，`sub` 为用户 UUID，签发方为 `zhizhou`，受众为 `zhizhou-api`。每次认证都验证固定算法、签名和声明，并从数据库确认账号存在且可用。客户端退出只清除令牌，已签发令牌到期前仍可能有效。

会话 ID 为后端生成的 UUID，统一命名 `conversation_id`。不存在、属于他人或已删除均返回 HTTP 404 和 `40401`，不暴露是否为他人所有。登录失败返回 401 和 `40102`，无效登录状态返回 401 和 `40101`，并保留 `WWW-Authenticate: Bearer`。重名注册返回 HTTP 200 和业务码 `20001`；参数错误为 422；会话忙为 409 和 `40901`。

### 最近记录与向前游标

两个读取接口均不接收页码或 OFFSET，也不返回总数、总页数。首次省略 `cursor`，默认取最近 20 条，`limit` 范围 1～100。`next_cursor` 是继续读取更早记录的版本化 Base64URL 文本，返回 `null` 表示当前没有更多记录；空字符串、非法编码或错误归属返回 422。

目录 `items` 每项含 `conversation_id / title / created_at / last_message_at`，按 `(last_message_at DESC, id DESC)` 排序，同时间使用 UUID 次键。最近消息时间在接受用户输入时更新，标题取首条消息去除首尾空白后的前 24 个字符。游标限定用户，查询始终过滤当前用户和软删除状态；Base64 不是授权或加密机制。目录为实时视图，向前读取期间收到新消息的旧会话可能前移，刷新后重新同步，不提供跨请求快照。

内容 `items` 为问答轮次，每项含 `turn_id / seq / user_content / assistant_content / assistant_message_id / public_events / status / error_code / created_at / updated_at / finished_at`。首次返回最近轮次，再携带游标读取更小的 `seq`；每批按 `seq` 正序返回，游标限定当前用户和当前会话。一个轮次包含一次用户输入、其公开行动与工具过程、最终回答。`status` 为 `running / completed / failed / interrupted`；部分回答保存在公开过程里，不冒充最终回答。

软删除只设置 `deleted_at`，保留轮次和 checkpoint；之后列表隐藏，内容及续聊返回 404。自己的已删除会话重复删除仍成功，他人的会话始终返回 404。生成期间拒绝删除，不自动取消；本期没有恢复、永久清理或单独创建会话接口。

### 业务数据与执行边界

三张业务表的实体定义见 [`app/models/entities.py`](app/models/entities.py)，首版迁移见 [`migrations/versions/0001_auth_conversations.py`](migrations/versions/0001_auth_conversations.py)：

| 表 | 主要字段与约束 |
| --- | --- |
| `users` | UUID 主键、唯一 username、password_hash、role、is_active、created_at、updated_at；角色 CHECK 约束 |
| `conversations` | UUID 主键、user_id 外键、title、last_message_at、created_at、updated_at、deleted_at；未删除会话的用户与复合排序部分索引 |
| `chat_turns` | UUID 主键、conversation_id 外键、seq、用户与最终助手正文、assistant_message_id、JSONB public_events、状态与错误码、时间；会话内 seq 唯一及状态 CHECK 约束 |

数据库时间为带时区时间，ID 由应用生成。仓储只执行 ORM 查询及 flush，由服务提交事务。公开历史从白名单 SSE 事件构造，`public_events` 是有序 `{event,data}` 数组，不含 start/done 或内部推理；相邻同一消息的 delta 合并，工具事件保持原顺序，成功确认后的最终正文独立保存，不在过程里重复。

聊天先取得跨进程 PostgreSQL advisory lock，再用短事务创建或核验会话、保存用户输入和 running 轮次，提交后发 start。生成期间不保持业务事务，工具边界立即保存快照，正文在收到增量时按一秒或累计 16 KiB 阈值提交。checkpoint 与业务历史分别提交，二者均完成后才发送 done；最终业务写入失败只发 error。

聊天与删除共用执行锁，同会话冲突立即 409，不同会话可并发。锁连接使用异步 SQLAlchemy、自动提交和 NullPool，退出时解锁并关闭物理连接，避免带锁连接返回池。启动和内容读取检查遗留 running 记录，仅在取得执行锁、确认没有活跃生成时标记 interrupted，不自动重放工具。取消尽力保存所有已接收公开内容；进程强制退出可能损失最后一次快照之后的片段。

业务会话通过 Agent 适配为带命名空间的内部 checkpoint key，框架配置键只保留在框架边界。旧的无归属 checkpoint 不删除，也不自动绑定任何用户；新 HTTP API 不开放这些记录。业务表与 checkpoint 不组成跨连接原子事务。

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

`--reload` 仅用于开发。统一入口通过可导入的事件循环工厂启动服务，Windows 普通启动和 reload 子进程均使用 psycopg 支持的 `SelectorEventLoop`，不修改全局事件循环 policy。

直接调用 Uvicorn 时，使用相同工厂，尤其不要在 Windows 普通启动时使用默认的 Proactor 循环：

```powershell
uv run uvicorn app.main:app --loop app.core.event_loop:create_event_loop --reload
```

此方式的日志在应用生命周期开始时统一，最早几条 Uvicorn 日志仍使用默认样式。

打开 [Swagger UI](http://127.0.0.1:8000/docs)，先注册、登录，再通过 Authorize 配置 JWT。首次调用 `POST /api/chat` 时只发送 `{"message":"你好"}`，从 start 保存后端签发的 ID。续聊请求示例：

```json
{
  "message": "刚刚聊了什么",
  "conversation_id": "00000000-0000-4000-8000-000000000001"
}
```

接口直接返回 SSE，HTTP `200`，`Content-Type: text/event-stream`，并设置 `Cache-Control: no-cache`、`X-Accel-Buffering: no`。每个事件由 `event:`、一行 JSON `data:` 和空行组成，JSON 中的换行会转义。例如：

```text
event: start
data: {"code":0,"message":"成功","data":{"conversation_id":"00000000-0000-4000-8000-000000000001","turn_id":"00000000-0000-4000-8000-000000000002","is_new":true}}

event: delta
data: {"code":0,"message":"成功","data":{"conversation_id":"00000000-0000-4000-8000-000000000001","message_id":"reply-1","text":"你好"}}

event: done
data: {"code":0,"message":"成功","data":{"conversation_id":"00000000-0000-4000-8000-000000000001","reply":"你好","message_id":"reply-1"}}

```

| 事件 | data 字段 | 含义 |
| --- | --- | --- |
| `start` | `conversation_id / turn_id / is_new` | 用户输入已提交，执行锁已取得 |
| `delta` | `conversation_id / message_id / text` | 当前助手消息的一段正文 |
| `tool_call` | `conversation_id / message_id / tool_call_id / name / arguments` | 模型已生成完整工具请求，尚不代表已执行 |
| `tool_start` | `conversation_id / tool_call_id / run_id / name / kind / arguments` | 工具实际开始执行，参数不包含框架注入值 |
| `tool_end` | `conversation_id / tool_call_id / run_id / name / kind / output` | 工具成功执行后的正文结果，不含 artifact |
| `tool_error` | `conversation_id / tool_call_id / run_id / name / kind / message` | 安全工具失败说明；执行前被拒绝时 run_id 为 null |
| `done` | `conversation_id / message_id / reply` | 最终助手完整回复，checkpoint 与业务最终结果均已提交 |
| `error` | `null` | 非零错误码和安全解释，本轮失败结束 |

`delta` 按 `message_id` 分组，可能包含工具调用前的助手说明；`done.reply` 是最终权威回答，不能简单把所有消息的增量拼成最终回答。公开进度说明使用普通 `delta`，不再提供 `reasoning_delta`；完整工具参数通过 `tool_call` 和 `tool_start` 输出，公开工具结果通过 `tool_end` 输出；不返回历史快照、模型推理字段、工具 artifact 或内部异常堆栈。图通过原生 `astream` 边生成边输出，并非完整生成后切片。成功事件 `code=0`，正常结束只发送一个 `done` 或 `error`；客户端断开时不保证终止事件。若传输提前结束但未收到终止事件，应视为未确认完成。

新增过程事件同样使用 `{code, message, data}` 外壳，正常交付的过程事件 `code=0`。`tool_error` 表示某一次工具调用失败，模型可能处理该失败后继续回复，因此客户端不能把它当成整轮终止；只有 `done` 或顶层 `error` 才终止本轮。未知工具和参数校验失败也会产生 `tool_error`，不会让 UI 永久等待工具结果。工具失败解释使用中央错误码的安全文案，不回传异常字符串。

例如，一次工具执行的事件数据如下（每帧后仍需空行）：

```text
event: delta
data: {"code":0,"message":"成功","data":{"conversation_id":"00000000-0000-4000-8000-000000000001","message_id":"plan-1","text":"我先查询上海的天气。"}}

event: tool_call
data: {"code":0,"message":"成功","data":{"conversation_id":"00000000-0000-4000-8000-000000000001","message_id":"plan-1","tool_call_id":"weather-1","name":"get_weather","arguments":{"city":"上海"}}}

event: tool_start
data: {"code":0,"message":"成功","data":{"conversation_id":"00000000-0000-4000-8000-000000000001","tool_call_id":"weather-1","run_id":"run-1","name":"get_weather","kind":"tool","arguments":{"city":"上海"}}}

event: tool_end
data: {"code":0,"message":"成功","data":{"conversation_id":"00000000-0000-4000-8000-000000000001","tool_call_id":"weather-1","run_id":"run-1","name":"get_weather","kind":"tool","output":"上海今天晴天，温度 25°C"}}

```

同一个工具请求用 `tool_call_id` 关联，`run_id` 标识实际执行次数；工具事件可以交错，并行工具谁先完成就先报告结果，不等待整个工具节点结束。`message_id` 将正文及完整调用请求关联到对应的模型消息；`done.reply` 仍只包含最终正文。参数是模型生成的完整 JSON，当前不对外发送尚未完成的参数字符串碎片，也不逐行转发命令 stdout/stderr。

当前仅注册 `get_weather` 演示工具。协议支持工具设置 `metadata={"display_kind": "command"}`，实际执行事件便带有 `kind="command"`，参数和结果沿用相同字段；这只是已注册工具的展示类型，本次未增加 Shell 执行器、任意系统命令执行能力或自动分类规则。普通工具默认 `kind="tool"`。

系统提示词要求每条包含工具调用的助手消息同时提供非空 `content`：详细说明当前处理什么、准备怎样使用工具和检查结果，以及与用户目标相关的判断依据、假设或取舍。同一消息包含多个并行调用时，正文须覆盖每个调用的用途。本轮首次调用还应介绍任务目标、交付结果、主要步骤与先后依赖、验证方式；后续调用根据实际结果说明发现与下一步，不重复整份规划。首次调用按当前用户消息计算，历史会话中的工具调用不免除本轮规划。公开依据是面向用户的决策摘要，不输出内部推理链，不虚构已执行的操作。

当前 `create_agent` 默认在模型不再返回工具调用时结束本轮，因此行动说明和规划必须与实际 `tool_calls` 放在同一条助手消息中，不能先单独发送计划再期待自动继续。无需工具时，在当前正文中直接给出完整答案或必要的澄清问题；工具执行后信息充足时直接完成回答，不为保持循环而调用无关工具。这是当前图的执行方式，不代表 LangChain 无法通过自定义图或中间件实现其他循环。

模型遗漏正文时，Agent 在 `tool_call` 之前补发同一 `message_id` 的中性说明“我准备调用 … 获取所需信息。”；不声明已经执行或成功，也不改写模型 checkpoint。该兜底仅标明将调用的工具，不替模型编造任务规划或判断依据。最终 `done.message_id` 标识应从过程区移出的最终正文，`done.reply` 为权威完整回答。详细规划和行动说明由提示词引导，当前没有内容完整性强制校验或自动重试机制；无需工具时，必要说明与答案仍属于同一正文，提示词不会创建额外的可折叠消息或阶段事件。

模型内部仍启用 DeepSeek 思考模式，并通过 `DeepSeekChatModel` 回传历史助手 `reasoning_content`，以维持工具后续步骤和多轮请求的兼容性；这些字段只在模型与 checkpoint 内部使用，不编码成 SSE。旧 checkpoint 缺失的字段按空字符串回传。公开工具及进度正文同时写入轮次快照，历史通过会话内容接口读取；本期不提供 SSE 事件重放或断点续传。

请求中的 `message` 必填且不能仅包含空白；`conversation_id` 是可省略或为 null 的 UUID，提供时必须通过归属校验。旧字段名及未知请求字段会被拒绝，空正文、非法 UUID 或 JSON 返回 HTTP `422` 和统一 JSON 错误响应。路由或依赖在流建立前发生的错误继续使用 JSON。SSE 开始后，模型、工具或持久化失败通过 `error` 报告，HTTP 状态保持 `200`：

```text
event: error
data: {"code":50001,"message":"对话执行失败，请稍后重试","data":null}

```

相同业务会话 ID 可继续自己的未删除会话，不同用户或不同会话的历史隔离；服务重启后仍可继续。HTTP 并发由数据库执行锁协调，Agent 内部锁只作为单实例的附加保护。身份、归属和执行冲突在 SSE 响应头发送前校验，流建立后发生的失败通过 error 结束。

客户端断开会关闭模型流，尽力保存公开过程并将未完成轮次标记 interrupted，不回滚已经写入的 checkpoint，不自动重试或重放工具。完整的失败和恢复语义见[业务数据与执行边界](#业务数据与执行边界)。

浏览器调用使用 POST fetch 响应流解析 SSE，代理需要关闭流缓冲。前端后续接入必须：注册登录并携带 JWT；停止自行生成会话 ID；首次请求从 start 取得 conversation_id；之后传回该 ID；从服务端游标加载列表、历史和删除状态。当前前端代码尚未适配新协议，不能直接匿名聊天；本期仅交付后端与接口文档。

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

错误码名称、数字及默认解释的唯一维护位置是[错误码目录](app/core/errors/codes.py)。业务码使用 `20000–29999`，新增真实功能时在该目录业务分组中添加唯一条目，再从业务逻辑抛出 `BusinessError`：

```python
from app.core.errors.codes import ErrorCode
from app.core.errors.exceptions import BusinessError

raise BusinessError(ErrorCode.BUSINESS_ERROR)
```

代码通过目录名称引用错误，不散落码值或自定义客户端解释。`BusinessError` 只接受已定义的业务码；`ServiceError` 接受已定义的系统码。异常定义不依赖 FastAPI，供 Agent、业务模块和命令行共用。当前只提供通用业务异常入口，尚未新增额度、权限等具体业务限制。

异常对象的 `error_code` 属性保存 `ErrorCode` 目录成员，可通过 `exc.error_code.code` 和 `exc.error_code.message` 读取数字码与解释；被包装的底层异常通过 `exc.__cause__` 查看。

参数校验统一使用 HTTP `422`；框架级 `404`、`405` 也返回统一格式，必要的 `Allow`、`WWW-Authenticate`、`Retry-After` 等响应头保留。其他 4xx 使用通用请求错误码。普通 `ValueError` 不会被当作业务失败：Agent 的模型调用失败、空回复等转为已知系统异常并保留原始异常链。

业务异常记录 `WARNING`，不输出堆栈；已知系统异常记录 `ERROR` 和堆栈。应用异常携带内部“已记录”标识，避免跨层重复记录。未知异常由全局处理器返回安全响应，Starlette 重抛后由 Uvicorn 记录原始堆栈。应用启动失败仍终止启动，不转换为业务响应。

该约定用于普通 JSON 业务接口；`/docs`、`/openapi.json`、文件下载和 SSE 聊天保持各自协议，不通过中间件读取并重写响应体。接口文档展示统一模型，并提供 HTTP `200` 下成功和业务失败的示例。

## 命令行智能体示例

在 `backend/` 目录运行：

```powershell
uv run python -m app.agents
```

编辑 `app/agents/__main__.py` 中的 `MESSAGE` 和 `CONVERSATION_ID` 后即可运行并打印回复。当前默认使用本地演示标识 `conversation-002` 和“刚刚说什么了”；重复运行沿用同一段演示状态，不会建立 HTTP 业务归属。原命令 `uv run python -m app.agents.agent` 仍可使用。

命令行是受信任的开发演示，直接调用 Agent，不通过 HTTP 用户归属层，也不会创建业务会话及轮次，不出现在 HTTP 会话目录中。它与 HTTP 共用配置、异步 checkpoint 管理和 Agent 实现，用同一个异步流聚合最终文本。命令行通过 Runner 和同一循环工厂运行，Windows 也使用 Selector 循环。成功输出纯文本回复，预期失败以退出码 `1` 结束，不重复异常日志。导入模块不连接外部服务。

## 统一日志

项目统一使用 Python 标准库 `logging`。配置位于 `app/core/logging.py`，环境读取与校验位于 `app/core/settings.py`；Web 启动入口、应用生命周期和智能体命令行入口显式初始化，导入模块不配置全局日志。

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
2026-10-13 15:30:04 INFO app.agents.agent 对话完成 conversation_id='00000000-0000-4000-8000-000000000001' duration_ms=1820.00
```

应用记录启动完成、启动失败和资源关闭。Agent 记录对话成功或失败、对话标识和耗时，计时包含等待对话锁的排队时间；业务失败无堆栈，系统失败保留堆栈。已知应用异常按“已记录”标识避免重复输出，未知异常由 Uvicorn 记录。默认不主动记录聊天正文、模型回复、思考文本、工具参数、工具输出、密钥或数据库连接串。本阶段不提供请求 ID、日志文件或第三方日志库。

各模块使用标准 logger，只记录自身事件，不添加 handler 或重新初始化日志：

```python
import logging

logger = logging.getLogger(__name__)
logger.info("业务事件")
```

集中配置会保留第三方 logger 的启用状态，并统一控制应用、Uvicorn 与第三方日志的输出级别。容器部署时由运行环境收集控制台日志。

## 测试

在 `backend/` 目录执行。默认运行全量测试，包含同一 PostgreSQL 实例上的真实数据库测试：

```powershell
uv run pytest -q
```

先按[配置与数据库](#配置与数据库)启动 PostgreSQL 并提供有效数据库连接配置，账号需要 CREATE DATABASE 权限。测试通过维护库 `postgres` 连接现有实例，每个数据库用例独享一个 `zhizhou_test_<随机值>` 临时库，执行正式 Alembic 迁移。模型和 JWT 使用测试配置，不需要真实模型密钥。连接、权限或迁移失败均报错，不会自动跳过。

数据库用例结束时先关闭客户端、checkpoint、业务引擎及锁连接，再删除本例成功创建的精确目标库；迁移失败和用例失败同样清理。不清空开发库、不复用固定测试库，也不通过外层事务回滚模拟真实提交。强制终止 Python 进程可能来不及清理临时库，后续测试不复用这些残留库。

| 命令 | 运行范围 |
| --- | --- |
| `uv run pytest -q` | 全部单元与集成测试，包含 PostgreSQL |
| `uv run pytest tests/unit -q` | 快速单元测试，无需数据库 |
| `uv run pytest tests/integration -q` | 全部集成测试 |
| `uv run pytest -m postgres -q` | 临时数据库、迁移与业务持久化 |
| `uv run pytest -m "not postgres" -q` | 显式运行无需数据库的全部测试 |
| `uv run pytest -m transport -q` | 真实回环 HTTP/SSE |
| `uv run pytest -m subprocess -q` | 独立解释器、日志及进程场景 |
| `uv run pytest --collect-only -q` | 仅收集用例，不连接数据库、不建库 |

### 目录与新增测试归属

- [`tests/unit/`](tests/unit/)：按 `core`、`schemas`、`agents`、`services`、`db`、`entrypoints` 划分单模块行为；`support` 验证共享测试支撑的清理与协议边界。
- [`tests/integration/`](tests/integration/)：按 `api`、`agents`、`services`、`runtime`、`transport`、`postgres` 验证真实组件协作。图使用内存 checkpoint 仍属于集成测试；MockTransport 驱动正式模型客户端也属于集成测试。
- [`tests/support/`](tests/support/)：可显式导入的应用装配、具名运行环境、SSE 解析、子进程和临时库管理；`fakes/` 放共享替身，`scripts/` 放独立解释器验证脚本。
- 根 `conftest.py` 仅提供后端路径和事件循环 fixture；子目录 fixture 只影响其实际使用范围，PostgreSQL 配置只在 `integration/postgres/conftest.py` 提供。测试不从 conftest 导入普通函数，不相互导入测试模块。

先确定验证边界，再按被测模块放置用例。同一文件围绕稳定行为组织，场景专属模型或工具留在用例附近，真实共享的辅助代码才进入 support。使用 `tests.support.*` 包路径导入，pytest 的 importlib 模式允许不同目录存在同名测试文件。

异步用例直接写为 `async def test_*` 并标记 `pytest.mark.anyio`。后端只使用 asyncio，由 function scope 的 `anyio_backend` 注入正式 `create_event_loop`，确保 Windows Psycopg、资源创建与释放使用同一循环。同步 CLI 和子进程测试保持同步；并发场景用事件控制时序并明确超时和清理。真实传输用例标记 `transport`，独立解释器标记 `subprocess`，数据库用例标记 `postgres`；未知标记会报错。

API 测试每例独立创建应用和依赖覆盖，生命周期用例复用正式 lifespan；OpenAPI 额外对比测试应用与正式入口，避免辅助装配偏离真实协议。不要用 TestClient 的完整响应断言代替实际 SSE 逐段传输验证。

### 覆盖的关键行为

集成测试覆盖注册竞争、JWT 声明与账号状态、ORM 约束和索引、Alembic 排除 checkpoint 表、两种角色所有权隔离、游标边界、公开工具历史、软删除、跨连接锁、取消清理、遗留状态恢复及最终提交失败。模型仍使用本地替身，不访问真实模型。其他测试覆盖配置优先级、资源释放、接口协议、导入无外部副作用，以及真实 LangChain 图的多轮对话和工具调用；日志配置在独立子进程中验证。

路由测试验证 `/api/chat` 的 SSE 事件、响应头、校验及流内错误、旧路径 `404`、错误方法 `405` 及 `Allow` 头、实例复用、依赖覆盖和 OpenAPI 示例。Agent 测试用可控异步事件验证首段先于完成、同会话 FIFO、跨会话并发、取消与异常后恢复、锁回收、最终落库边界，以及真实图取消时保留用户输入但不保存半段助手回复。

错误处理测试覆盖码值唯一性、业务码类型与范围、成功数据类型、业务失败 HTTP `200`、参数与协议错误、响应头保留、未知异常与响应模型校验失败，以及 CLI 退出码和异常日志不重复。另用短暂启动的本地 Uvicorn 服务验证兜底响应和实际堆栈输出，测试完成即关闭服务；该测试也不依赖模型或数据库。

SSE 专项测试另在临时回环端口启动本地 Uvicorn，使用真实 HTTP 客户端验证首段增量在生成完成前到达、流中失败和客户端断开取消；完成后关闭客户端、服务器与套接字。模拟 ASGI 2.0/2.4 覆盖排队、模型等待、发送失败和服务器取消时的异步清理；普通启动及 reload 配置均核对事件循环工厂。

过程事件测试使用真实图验证并行工具独立完成、命令类型标记、工具参数和结果、可恢复及不可恢复错误、执行前拒绝、artifact 排除及工具执行取消。模型适配测试通过 MockTransport 模拟 DeepSeek HTTP SSE，由正式客户端解析内部思考及工具参数碎片，验证推理不外发、缺少正文时的兜底顺序，并核验 checkpoint 和工具后续、多轮请求中的 reasoning_content 回传，不访问真实模型。

真实模型验收先注册登录，在首次 start 取得会话 ID，再于同一 `conversation_id` 告知姓名并追问姓名；省略 ID 创建另一会话确认历史隔离，重启服务后使用原标识继续对话。测试模型的实际回复不应作为固定文本断言。

## 目录职责

- `app/__main__.py`：统一 Web 启动入口，处理地址、端口、reload 参数并向 Uvicorn 传递日志配置。
- `app/main.py`：FastAPI 应用、启动/退出资源管理、全局异常处理器注册和 API 总路由挂载。
- `app/agents/`：Agent 专属实现；`models.py` 创建支持思考回传的模型，`events.py` 适配工具生命周期，`prompts.py` 定义提示词，`tools/` 定义工具，`factory.py` 组装 Agent，`agent.py` 执行对话，`__main__.py` 提供命令行示例。
- `app/core/`：Web、CLI 与其他后端模块共用的基础能力；`settings.py` 读取和校验配置，`logging.py` 集中配置标准日志，`event_loop.py` 创建兼容 Psycopg 的事件循环，`errors/` 维护错误码、应用异常和异常日志责任。
- `app/db/`：异步业务引擎、迁移版本校验、跨进程会话执行锁，以及独立管理的 checkpoint 资源。
- `app/schemas/`：聊天请求、聊天数据模型及通用响应模型和构建函数。
- `app/api/`：API 总路由、公共请求依赖、按业务划分的子路由、SSE 编码与断开清理，以及统一异常处理器和错误响应文档；结构与扩展步骤见[分级 API 路由](#分级-api-路由)。
- `app/models/`：SQLAlchemy 业务实体。
- `app/repositories/`：无隐式提交的异步 ORM 读写，事务提交由业务服务负责。
- `app/services/`：认证、会话所有权、游标读取及轮次持久化；具体 SQL 查询交给仓储，HTTP/SSE 编码交给 API 层。
- `app/utils/`：预留不包含业务规则的通用辅助函数，当前尚无具体实现；游标、SSE 编码和数据库锁仍归属各自模块。
- `migrations/`：Alembic 异步环境和版本迁移，仅管理业务表。
- `tests/`：按单元与集成层级组织测试，共享支撑位于 `tests/support/`；归属、资源隔离和运行命令见[测试](#测试)。

后续开发外部服务接入时，再按需添加 `app/integrations/`。

`core` 不反向依赖 API、业务服务或具体 Agent；各入口显式调用配置和日志初始化函数，导入核心模块不会连接数据库或调用模型。HTTP 异常响应转换仍由 `app/api/exception_handlers.py` 负责。新增代码优先放在职责明确的模块中，不因被多个位置调用就移入 `core` 或 `utils`。

接口和智能体工具应复用业务服务，由服务执行文件访问与知识检索的权限校验。

项目使用平铺的 `app/` 包布局，已在 `pyproject.toml` 中显式配置 uv 的包发现路径。
