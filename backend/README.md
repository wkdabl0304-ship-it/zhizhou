# 知舟后端

使用 Python 3.14 及以上版本和 uv 管理后端项目。当前已实现账号密码注册、JWT 登录、RBAC 与资源范围权限、用户和部门管理、用户会话隔离、游标读取最近及更早的会话和历史、软删除、AI 自动标题与手动改名，以及异步 SSE 聊天与公开工具过程持久化。业务数据使用 SQLAlchemy 2.1 异步 ORM 与 Alembic，模型上下文由 LangGraph 的 PostgreSQL checkpoint 独立保存。模型通过供应商层和模型处理层接入 OpenAI、Anthropic、DeepSeek 与阿里云百炼，可经接口维护全局供应商配置、模型方案和默认选择，不对外返回模型推理。天气工具返回固定演示内容。

前端已接入注册、登录、当前用户校验及服务端会话目录、游标历史、流式续聊和软删除。页面、身份生命周期及跨窗口生成的交互边界见[前端文档](../frontend/README.md#页面与聊天边界)，也可通过 Swagger 或 HTTP 客户端验收接口。

共享文件后端已提供全局、部门、个人空间、目录新建和浏览、原文件上传下载、重命名和递归删除，以及可在线配置的范围上传上限。尚无文件管理页面、聊天附件、预览或 RAG；接口、数据字典和运维说明统一见[共享文件接口](docs/files-api.md)。

项目定位和功能规划见[根 README](../README.md)。前后端已接通供应商连接/模型启停、受限推理策略和按会话保存选择；界面状态恢复见[前端文档](../frontend/README.md#模型管理)，后端契约见[模型配置接口](#模型配置接口与两层适配)。

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

- `MODEL_CONFIG_ENCRYPTION_KEY`：必填的独立 Fernet 主密钥，只用于加密数据库中的模型凭据；供应商 API Key 通过模型配置接口写入，不放入 `.env`。
- `POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB`：数据库连接参数；示例提供本地开发用值。若通过系统环境变量覆盖，确保与数据库启动配置一致。
- `POSTGRES_PORT`：智能体连接的宿主机端口。Compose 当前固定映射 `5432:5432`，修改此变量时还需要相应修改 Compose 端口映射。
- `POSTGRES_HOST`：默认 `127.0.0.1`，显式提供时不能为空。
- `JWT_SECRET`：必填，至少 32 字节的独立随机密钥，没有默认值；不要填写示例密码或提交到 Git。
- `JWT_TTL_SECONDS`：默认 `7200`，必须为正整数；过期后重新登录，不提供刷新令牌；停用和改密通过凭据版本撤销旧令牌。
- `FILE_STORAGE_ROOT`：默认 `.data/files`，相对路径基于 `backend/`；用于私有原文件，启动时验证可写，多进程须指向同一目录。上传大小通过文件策略接口配置。

配置加密主密钥、数据库用户、密码、库名、端口及 JWT 密钥必填且不能仅包含空白；端口范围为 1–65535。供应商配置使用后端登记的官方端点，不接收任意地址。可运行 `uv run python -c "import secrets; print(secrets.token_urlsafe(48))"` 生成独立随机 JWT 密钥，再保存到本地 `.env`。

可在 `backend/` 执行 `uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` 生成加密主密钥并保存到本地 `.env`。主密钥需要与数据库分开稳定备份；更换部署主密钥不会自动重新加密旧凭据。旧 `DEEPSEEK_API_KEY` 不再读取或自动导入。

配置无效、业务表未迁移、版本不匹配或数据库无法连接时，服务启动失败。未配置默认模型不阻止启动、登录、读取历史和管理配置；只有既无会话选择又无有效默认时，聊天才在建立 SSE、创建会话与轮次前返回 `503 / 50301`，明确选择有效方案仍可发送。首次启动前在 `backend/` 执行：

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
| `POST /api/auth/register` | `{username,password,role?:"user"}` | 公开身份及 `created_at` |
| `POST /api/auth/login` | `{username,password}` | `{access_token,token_type,expires_in,user}` |
| `GET /api/auth/me` | Bearer JWT | `{id,username,role,department,roles,grants}` |
| `GET /api/conversations` | `limit=20&cursor=...` | `{items,next_cursor}` |
| `GET /api/conversations/{conversation_id}` | `limit=20&cursor=...` | `{conversation,items,next_cursor}` |
| `DELETE /api/conversations/{conversation_id}` | 无请求体 | `null` |
| `PATCH /api/conversations/{conversation_id}/title` | `{title}`，规范化后 1–100 字符 | 更新后的会话信息，允许生成中改名 |
| `PATCH /api/conversations/{conversation_id}/model-selection` | `{model_selection_version,model_selection}` | 更新后的会话信息 |
| `POST /api/chat` | `{message,conversation_id?,model_selection?,model_selection_version?}` | SSE，首轮选择与续聊版本不能混用，见[聊天接口](#启动与聊天接口) |

注册成功后单独登录。用户名去除首尾空白并转小写，限定 3～32 位 ASCII 字母、数字或下划线；密码 8～128 个字符，不去除空格，使用 Argon2 摘要，哈希与校验在线程池执行。公开注册只创建无部门普通用户，拒绝指定管理角色。所有身份只能操作自己的个人会话。部门、用户管理和角色任免接口、逐字段数据库说明见[权限对接文档](docs/authorization-api.md)。

JWT 使用 HS256，必需声明为 `sub / iat / exp / iss / aud / token_version`，`sub` 为用户 UUID，签发方为 `zhizhou`，受众为 `zhizhou-api`。每次认证验证签名、声明、账号启停和最新凭据版本；角色和权限不写入 JWT。客户端退出只清除本地令牌；停用和改密撤销既有令牌，旧版本无凭据版本声明的 JWT 需重新登录。

首次初始化：先注册启用账号，再在 `backend/` 执行 `uv run python -m app.manage grant-super-admin <用户名>`。命令可重复执行，仅本地运维可用；没有免认证 HTTP 初始化接口。在线操作保护最后一名可用超管。详见[运维与迁移](docs/authorization-api.md#错误并发和运维)。

会话 ID 为后端生成的 UUID，统一命名 `conversation_id`。不存在、属于他人或已删除均返回 HTTP 404 和 `40401`，不暴露是否为他人所有。用户名或密码错误返回 401 和 `40102`；正确密码登录停用账号或有效 JWT 认证时发现账号停用返回 401 和 `40103`（账号已被停用，请联系管理员），无效登录状态返回 401 和 `40101`，并保留 `WWW-Authenticate: Bearer`。重名注册返回 HTTP 200 和业务码 `20001`；参数错误为 422；会话忙为 409 和 `40901`。

### 最近记录与向前游标

两个读取接口均不接收页码或 OFFSET，也不返回总数、总页数。首次省略 `cursor`，默认取最近 20 条，`limit` 范围 1～100。`next_cursor` 是继续读取更早记录的版本化 Base64URL 文本，返回 `null` 表示当前没有更多记录；空字符串、非法编码或错误归属返回 422。

目录 `items` 每项含 `conversation_id / title / created_at / last_message_at`，按 `(last_message_at DESC, id DESC)` 排序，同时间使用 UUID 次键。最近消息时间在接受用户输入时更新，标题变更不改变排序。标题生命周期见[自动标题与手动改名](#自动标题与手动改名)。游标限定用户，查询始终过滤当前用户和软删除状态；Base64 不是授权或加密机制。目录为实时视图，向前读取期间收到新消息的旧会话可能前移，刷新后重新同步，不提供跨请求快照。

内容 `items` 为问答轮次，每项含 `turn_id / seq / user_content / assistant_content / assistant_message_id / public_events / status / error_code / created_at / updated_at / finished_at`。首次返回最近轮次，再携带游标读取更小的 `seq`；每批按 `seq` 正序返回，游标限定当前用户和当前会话。一个轮次包含一次用户输入、其公开行动与工具过程、最终回答。`status` 为 `running / completed / failed / interrupted`；部分回答保存在公开过程里，不冒充最终回答。

软删除只设置 `deleted_at`，保留轮次和 checkpoint；之后列表隐藏，内容及续聊返回 404。自己的已删除会话重复删除仍成功，他人的会话始终返回 404。生成期间拒绝删除，不自动取消；本期没有恢复、永久清理或单独创建会话接口。

### 自动标题与手动改名

新会话先把首条问题中的连续空白合并成一个空格、去除首尾空白，再取前 24 个 Unicode 字符作为临时标题。回答成功保存后，用本轮固定的模型快照概括首条问题与本次回答：问题、回答各最多取 2,000 字符，目标标题不超过 20 字，规范化后必须为 1–100 字符。标题模型独立调用，不绑定工具，不读取或写入聊天 checkpoint，不把标题或内部推理保存到公开聊天历史。

整个标题阶段（查询、调用、保存）共用 15 秒期限；异常、空白或超长输出均保留临时标题并照常发送 `done`，不回滚成功回答。后续成功轮次用首条问题和当前回答重试，正式标题生成后停止。客户端在标题阶段断开时关闭模型资源，已经保存的轮次仍是 `completed`，之后可继续重试标题；尚未完成回答时断开仍按原规则保存为 `interrupted`。

```http
PATCH /api/conversations/7bcd0b65-c775-4dc3-baf3-46d433a620ba/title
Authorization: Bearer <access_token>
Content-Type: application/json

{"title":"Vue 项目结构与模块划分"}
```

请求只允许 `title` 字符串，去除首尾空白并合并连续空白（含换行）后校验 1–100 字符；拒绝 `null`、非字符串、空白、超长及额外字段。成功返回 `{code:0,message:"成功",data:ConversationInfo}`，与目录单条结构一致，包含 `conversation_id / title / created_at / last_message_at / model_selection / model_selection_version / model_selection_issue`，不公开内部标题来源。

该接口只更新当前用户未删除的会话。未登录返回 `401 / 40101`；不存在、已删除或属于他人的会话统一 `404 / 40401`；非法 UUID 或请求体返回 `422 / 42200`；系统故障沿用 `500 / 50000`。生成期间也可改名，不取得聊天执行锁，不调用模型，不改变最近消息时间或模型选择；即使提交相同标题，也停止自动覆盖。多个手动请求按数据库实际写入顺序生效。

内部 `title_source` 为 `provisional / auto / manual`。自动保存仅匹配当前用户、未删除且仍为 `provisional` 的行；手动修改原子写入 `manual`，因此无论自动和手动更新按哪种顺序完成，最终均保留手动标题。模型等待期间不占用业务事务，读取和条件保存分别使用短事务。

标题迁移 `0005_conversation_titles` 在已有 `conversations` 中增加 `title_source VARCHAR(20) NOT NULL DEFAULT 'manual'` 及枚举 CHECK，不增加表或索引；旧标题原样保留并保护为 `manual`，新建会话显式写入 `provisional`。升级执行 `uv run alembic upgrade head`；降级仅移除来源字段及约束，保留当前标题。

SSE 事件及字段保持现状，标题处理结束后才发送 `done`；收到后从会话列表的 `data.items[].title` 或详情的 `data.conversation.title` 读取最终标题。本期前端尚未提供改名入口或聊天完成后的标题刷新，现有目录刷新仍可读取新标题；不提供手动重新生成接口。

### 业务数据与执行边界

认证与会话三张业务表的实体定义见 [`app/models/entities.py`](app/models/entities.py)，首版迁移见 [`migrations/versions/0001_auth_conversations.py`](migrations/versions/0001_auth_conversations.py)：

| 表 | 主要字段与约束 |
| --- | --- |
| `users` | UUID 主键、唯一 username、password_hash、is_active、department_id、token_version、created_at、updated_at；部门外键和凭据正整数约束 |
| `file_spaces / file_upload_policies / file_blobs / file_entries` | 文件空间归属、范围上传策略、原件生命周期及目录树；字段、状态和约束见[文件数据字典](docs/files-api.md#数据字典) |
| `departments / roles / permissions / role_permissions / user_roles` | 部门、角色目录、操作目录、范围模板和用户角色绑定；字段与约束统一见[权限数据模型](docs/authorization-api.md#数据库逐字段说明) |
| `conversations` | UUID 主键、user_id 外键、title、title_source、last_message_at、created_at、updated_at、deleted_at；标题来源 CHECK；未删除会话的用户与复合排序部分索引 |
| `chat_turns` | UUID 主键、conversation_id 外键、seq、用户与最终助手正文、assistant_message_id、JSONB public_events、状态与错误码、时间；会话内 seq 唯一及状态 CHECK 约束 |

数据库时间为带时区时间，ID 由应用生成。仓储只执行 ORM 查询及 flush，由服务提交事务。公开历史从白名单 SSE 事件构造，`public_events` 是有序 `{event,data}` 数组，不含 start/done 或内部推理；相邻同一消息的 delta 合并，工具事件保持原顺序，成功确认后的最终正文独立保存，不在过程里重复。

聊天先取得跨进程 PostgreSQL advisory lock，再用短事务创建或核验会话、保存用户输入和 running 轮次，提交后发 start。生成期间不保持业务事务，工具边界立即保存快照，正文在收到增量时按一秒或累计 16 KiB 阈值提交。checkpoint 与业务历史分别提交，二者均完成并结束本次标题处理后才发送 done；最终业务写入失败只发 error。

聊天与删除共用执行锁，同会话冲突立即 409，不同会话可并发。锁连接使用异步 SQLAlchemy、自动提交和 NullPool，退出时解锁并关闭物理连接，避免带锁连接返回池。启动和内容读取检查遗留 running 记录，仅在取得执行锁、确认没有活跃生成时标记 interrupted，不自动重放工具。取消尽力保存所有已接收公开内容；进程强制退出可能损失最后一次快照之后的片段。

业务会话通过 Agent 适配为带命名空间的内部 checkpoint key，框架配置键只保留在框架边界。旧的无归属 checkpoint 不删除，也不自动绑定任何用户；新 HTTP API 不开放这些记录。业务表与 checkpoint 不组成跨连接原子事务。

## 模型配置接口与两层适配

可通过前端[模型管理页面](../frontend/README.md#模型管理)操作，也可在 `/docs` 登录授权后验收接口。配置管理及目录要求 `model:manage@global`，普通用户保留 `model:use` 和 `/api/model-config/options`。前端按有效授权控制路由、导航和操作，服务端仍独立检查并在无权限时返回 `40301`；模型全局配置不改变聊天历史的用户所有权。

首次设置按以下顺序执行：**创建供应商配置 → 创建模型方案 → 可选测试 → 设置默认或在首轮明确选择**。保存和设为默认都只做本地校验，只有显式测试或聊天才调用上游。前端聊天页支持手动选择有效方案，无全局默认也能发送。

### 供应商层与模型处理层

- `app/llm/providers/` 使用 `langchain-openai.ChatOpenAI`、`langchain-anthropic.ChatAnthropic`、`langchain-deepseek.ChatDeepSeek` 和 `langchain-qwq.ChatQwen`；负责官方服务接入、原生流和异常边界，不读取数据库。Qwen 包是 LangChain 文档收录的社区专用集成。
- `app/llm/models/catalog.py` 登记精确模型 ID、支持格式、推理方式与应用允许上限，`policy.py` 按具体模型转换参数。前端目录来自这里，不获取上游模型列表，不按未知名称推断能力。
- `app/llm/models/history.py` 在请求边界投影兼容历史，并在 checkpoint 消息中标记供应商配置、密钥版本、模型和格式来源；`runtime.py` 按本轮快照组装现有 Agent。
- 首期目录覆盖 GPT-6 通用系列（含 6.1 Sol）与 GPT-5.6 Sol/Terra/Luna、Claude Opus 5.5/5、Sonnet 5.5/5、Haiku 5.5/4.5、DeepSeek Flash/Pro、Qwen Max/Plus/Flash 的当前与上一代主力模型。退役模型不作为独立选项；不接入其他托管品牌、多模态输入或供应商内置工具。
- OpenAI 默认 Responses；Chat Completions 只开放能运行本项目工具的组合。GPT-6 Sol/Luna 在 Chat 下仅开放关闭思考，Astra 和 6.1 Sol 仅开放 Responses。
- 推理按模型支持 `default / off / effort / budget` 中的适用形式。目录提供真实档位、预算范围、应用默认值与预算/输出上限关系；Qwen 3.8 的 effort 和预算分别使用，不能同时传入。`max_output_tokens` 是本项目允许的上限，可能低于供应商完整能力。

安装版本以 `uv.lock` 为准。新增 `langchain-anthropic 1.7.5`、`langchain-qwq 0.3.5`，保留原 OpenAI/DeepSeek 版本。Anthropic SDK 明确要求 `>=1.17,<2` 并使用 `httpx2`，其他 SDK 使用 `httpx`；供应商上下文分别创建和关闭正确类型的客户端，不关闭集成包中可能跨请求共享的 HTTP 缓存。

### 数据表与一致性

实体位于 `app/models/model_config.py`，模型选择迁移为 `0004_model_selection`；`0005_conversation_titles` 增加[标题来源](#自动标题与手动改名)，`0006_authorization` 增加权限表和用户凭据版本，当前最新迁移 `0007_file_spaces` 增加文件空间与原件生命周期。模型目录不入库，用户保存的模型方案才入库。

供应商配置保存品牌、API 格式、官方端点及 API Key；模型方案引用供应商配置，再选择具体模型和推理设置。升级执行 `uv run alembic upgrade head`，迁移保留已有配置、默认引用和轮次快照；原方案默认启用且推理固定，旧会话选择为空。接口统一使用 `/provider-configurations`，引用字段为 `provider_configuration_id`。

| 表 | 字段与约束 |
| --- | --- |
| `provider_configurations` | UUID 主键、名称、品牌、格式、端点 JSONB、加密密钥、凭据版本、配置版本和时间；新增 `enabled BOOLEAN NOT NULL DEFAULT true`。格式与供应商组合、JSON 对象和正版本受 CHECK 约束。 |
| `model_configurations` | UUID 主键、供应商配置 FK RESTRICT 及索引、名称、目录 ID、推理 JSONB、输出上限（默认 16384）、版本和时间；新增 `enabled`（默认 true）、`reasoning_policy JSONB`（默认 fixed）。策略为对象且模式只能 fixed/selectable；输出上限、版本为正。 |
| `chat_model_settings` | `id SMALLINT PK CHECK(id=1)`；`model_configuration_id UUID NULL FK RESTRICT`；`version INTEGER`；`updated_at TIMESTAMPTZ`。迁移初始化唯一行，默认引用为空。 |
| `conversations` 选择字段 | `model_selection JSONB NULL` 保存方案 ID 和具体推理值，不建立方案外键；`model_selection_version INTEGER NOT NULL DEFAULT 1` 为正。允许配置删除后保留失效选择，不增加 JSONB 索引。 |
| `chat_turns.model_snapshot` | 可空 JSONB，保存本轮供应商配置/模型版本、供应商、模型 ID、格式、具体 `reasoning` 及实际参数，不含明文密钥、密文或主密钥；旧轮次不补写。 |

供应商配置的供应商、模型方案的供应商配置归属创建后固定；需要更换时新建配置。`credential_revision` 仅在替换 API Key 时递增，普通名称修改只递增 `version`。API Key 使用 Fernet 认证加密，接口只返回 `api_key_configured`；PATCH 省略密钥表示保留，null 或空白被拒绝。

所有配置写事务先锁定单例设置行，随后校验目标资源版本与引用，防止检查后被其他写请求插入关联；网络调用不持这个锁。模型快照用单条联表查询取得，业务事务在访问供应商前结束。已有会话保存独立选择，不跟随全局默认切换；供应商及方案配置在下一轮重新验证，失效时要求重选，不影响已接受轮次及工具后续步骤。

推理策略由 `app/llm/models/selection.py` 验证，选项、批量失效判断和快照装配由 `app/services/model_selection.py` 承担，配置 CRUD 留在原模型配置服务。会话的选择保存、版本和跨进程锁由会话服务负责，避免继续将运行装配堆入配置管理。目录/详情响应增加选择、选择版本和动态失效原因，切换选择不改变最近消息时间。接口结构见下节，界面状态恢复见[前端文档](../frontend/README.md#模型管理)。

### 接口契约

以下路径统一加 `/api/model-config` 前缀，全部要求 Bearer JWT；响应沿用 `{code,message,data}`。目录和配置响应具有对应 OpenAPI 类型，凭据不会出现在公开响应中。

| 方法与路径 | 请求或筛选 | 成功 data |
| --- | --- | --- |
| `GET /catalog/providers` | 无 | 供应商数组，含格式、官方端点；旧地域及业务空间选项仅作接口兼容 |
| `GET /catalog/models` | 可选 `provider`、`api_format` | 模型数组，含 `catalog_model_id`、格式、能力、推理控件、允许输出上限 |
| `GET /options` | 无 | 同一查询快照下有效默认和按连接分组的受限聊天选项，不含端点及凭据 |
| `GET /provider-configurations` | 无 | 全局供应商配置数组 |
| `POST /provider-configurations` | 创建供应商配置体，见下例 | 新供应商配置详情及 `version=1` |
| `GET /provider-configurations/{id}` | UUID | 安全供应商配置详情 |
| `PATCH /provider-configurations/{id}` | `version` 及待修改字段，不允许 `provider` | 新版本供应商配置详情 |
| `DELETE /provider-configurations/{id}` | 必填查询参数 `version` | `null`，需先删除关联模型 |
| `GET /models` | 可选 `provider_configuration_id` | 保存的方案，含原生能力、`enabled`、`reasoning_policy`、`available` 和 `selectable` |
| `POST /models` | 模型方案体，见下例 | 新方案及 `version=1` |
| `GET /models/{id}` | UUID | 方案及当前目录能力 |
| `PATCH /models/{id}` | `version` 与名称、目录模型、推理、输出上限、启停或完整推理策略 | 新版本方案 |
| `DELETE /models/{id}` | 必填查询参数 `version` | `null`，不能直接删除当前默认 |
| `GET /default` | 无 | 默认引用、版本、更新时间及可选模型概要 |
| `PUT /default` | `version`、`model_configuration_id` | 更新后的默认；模型 ID 为 null 表示清除 |
| `POST /models/{id}/test` | 无请求体 | `latency_ms`、`provider_configuration_version`、`model_version`、`verified=streaming_text` |

创建供应商配置示例：

```json
{
  "name": "DeepSeek 官方",
  "provider": "deepseek",
  "api_format": "chat_completions",
  "endpoint_config": {"endpoint_id": "official"},
  "api_key": "替换成真实模型密钥"
}
```

OpenAI、Anthropic、DeepSeek 的 `endpoint_id` 为 `official`。百炼直接填写控制台的 **OpenAI 兼容地址**，不需要单独选择地域或填写业务空间：

```json
{
  "name": "我的百炼",
  "provider": "bailian",
  "api_format": "chat_completions",
  "endpoint_config": {
    "base_url": "https://ws-example.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
  },
  "api_key": "仅用于说明的占位值"
}
```

保存时清除地址首尾空白和末尾斜杠，仅接受 HTTPS 百炼官方业务空间域名及北京/新加坡公共兼容域名，路径须为 `/compatible-mode/v1`；拒绝带凭据、额外端口、查询参数、片段及原生 DashScope `/api/v1` 的地址。其他供应商仍使用既定官方端点；接口不接受任意第三方 URL、自定义请求头或额外字段。

旧版百炼 `endpoint_id + workspace_id` 请求及已保存 JSON 继续兼容。读取时返回等价 `endpoint_config.base_url`，不写库、不改变版本或密钥；下次保存时转换为地址 JSON。继续复用 `endpoint_config JSONB` 列，无需新增数据库迁移，也无需重新创建已有模型或默认引用。地址变化只递增配置版本，省略 API Key 时保留原密钥和 `credential_revision`。

创建模型方案示例，`provider_configuration_id` 替换为创建供应商配置返回的 UUID：

```json
{
  "name": "DeepSeek 深入思考",
  "provider_configuration_id": "7df7c7f4-7228-41bf-8981-a785dca3ef62",
  "catalog_model_id": "deepseek:deepseek-flash",
  "reasoning": {"mode": "effort", "effort": "high"},
  "max_output_tokens": 16384
}
```

其他推理形式分别为 `{"mode":"default"}`、`{"mode":"off"}` 和 `{"mode":"budget","budget_tokens":4096}`，仅在目录声明支持时合法。Claude 手动预算至少 1024 且必须小于本方案的输出上限。读取模型目录可获得 `budget_must_fit_output`，前端无需自行维护这些规则。

设置默认示例，版本取 `GET /default`，模型 UUID 取创建方案的结果：

```json
{
  "version": 1,
  "model_configuration_id": "58a613c4-5286-468f-b345-d526ec776139"
}
```

更新必须携带读取时的版本，成功递增；PATCH 显式 null 和空修改被拒绝。过期版本返回 `409 / 40902`；引用冲突或供应商配置修改导致已有模型不兼容返回 `409 / 40903` 并整体回滚；资源不存在分别为 `40402 / 40403`；非法组合返回 `422 / 42200`。

模型测试使用固定短提示，只验证该次文本流可完成，不执行天气等业务工具、不创建聊天历史、不自动设置默认。真实调用可能产生供应商费用。上游鉴权、限流/额度、超时及其他预期失败分别使用业务码 `20002 / 20003 / 20004 / 20005`，HTTP 仍为 200；不会因上游 401 令用户退出登录，也不回传供应商原始响应。

管理测试允许测试停用方案，使用方案默认推理。配置元数据、启停和凭据轮换可独立于模型目录管理；端点/格式修改仍校验全部关联方案，运行参数和策略修改仍要求完整有效。错误码以 `app/core/errors/codes.py` 为准，前端恢复规则见[前端文档](../frontend/README.md#模型管理)。

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

模型内部按保存的推理方案运行。DeepSeek 通过 `DeepSeekChatModel` 回传历史助手 `reasoning_content`，Claude 保留同源思考签名，Responses 保留同源推理块；这些字段只在模型与 checkpoint 内部使用，不编码成 SSE。跨模型或凭据变化时只向目标模型投影公开文本和完整工具调用/结果对；原 checkpoint 不被覆盖，未完成工具尾部不会伪造成已完成调用。旧 DeepSeek checkpoint 缺失的思考字段按空字符串回传。公开工具及进度正文同时写入轮次快照，历史通过会话内容接口读取；本期不提供 SSE 事件重放或断点续传。

请求中的 `message` 必填且不能仅包含空白；`conversation_id` 是可省略或为 null 的 UUID，提供时必须通过归属校验。旧字段名及未知请求字段会被拒绝，空正文、非法 UUID 或 JSON 返回 HTTP `422` 和统一 JSON 错误响应。路由或依赖在流建立前发生的错误继续使用 JSON。SSE 开始后，模型、工具或持久化失败通过 `error` 报告，HTTP 状态保持 `200`：

```text
event: error
data: {"code":50001,"message":"对话执行失败，请稍后重试","data":null}

```

相同业务会话 ID 可继续自己的未删除会话，不同用户或不同会话的历史隔离；服务重启后仍可继续。HTTP 并发由数据库执行锁协调，Agent 内部锁只作为单实例的附加保护。身份、归属和执行冲突在 SSE 响应头发送前校验，流建立后发生的失败通过 error 结束。

客户端断开会关闭模型流，尽力保存公开过程并将未完成轮次标记 interrupted；回答已保存、仅在等待标题时断开，轮次保持 completed。不回滚已经写入的 checkpoint，不自动重试或重放工具。完整的失败和恢复语义见[业务数据与执行边界](#业务数据与执行边界)。

浏览器调用使用 POST fetch 响应流解析 SSE，代理需要关闭流缓冲。前端聊天与会话请求携带 Bearer JWT；首次聊天省略会话 ID，从 start 取得 conversation_id，续聊时传回该 ID；目录和历史按服务端游标读取，删除成功后更新界面。客户端通过历史读取接口自动同步远端 running 快照，服务端不提供 SSE 重放。具体同步时机和页面行为统一维护在[前端文档](../frontend/README.md#页面与聊天边界)。

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

代码通过目录名称引用错误，不散落码值或自定义客户端解释。`BusinessError` 只接受已定义的业务码；`ServiceError` 接受已定义的系统码。异常定义不依赖 FastAPI，供 Agent、业务模块和命令行共用。权限与管理冲突使用明确的 403、404、409 错误，详见[权限错误目录](docs/authorization-api.md#错误并发和运维)；额度限制尚未实现。

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

文件专项执行 `uv run pytest tests/integration/postgres/files tests/integration/api/test_files.py tests/integration/transport/test_file_transfers.py -q`。真实数据库和 E2E 的原件目录跟随随机库生命周期隔离，重启测试保留同一临时目录，结束时清理；不会使用开发原文件。单元测试同时覆盖名称、磁盘路径、大小边界、空间权限及清理任务生命周期。
- 根 `conftest.py` 仅提供后端路径和事件循环 fixture；子目录 fixture 只影响其实际使用范围，PostgreSQL 配置只在 `integration/postgres/conftest.py` 提供。测试不从 conftest 导入普通函数，不相互导入测试模块。

先确定验证边界，再按被测模块放置用例。同一文件围绕稳定行为组织，场景专属模型或工具留在用例附近，真实共享的辅助代码才进入 support。使用 `tests.support.*` 包路径导入，pytest 的 importlib 模式允许不同目录存在同名测试文件。

异步用例直接写为 `async def test_*` 并标记 `pytest.mark.anyio`。后端只使用 asyncio，由 function scope 的 `anyio_backend` 注入正式 `create_event_loop`，确保 Windows Psycopg、资源创建与释放使用同一循环。同步 CLI 和子进程测试保持同步；并发场景用事件控制时序并明确超时和清理。真实传输用例标记 `transport`，独立解释器标记 `subprocess`，数据库用例标记 `postgres`；未知标记会报错。

API 测试每例独立创建应用和依赖覆盖，生命周期用例复用正式 lifespan；OpenAPI 额外对比测试应用与正式入口，避免辅助装配偏离真实协议。不要用 TestClient 的完整响应断言代替实际 SSE 逐段传输验证。

### 前端 E2E 隔离后端

`tests/support/e2e.py` 是前端 Playwright 的本地启动入口，命令、浏览器安装和用例选择统一维护在[前端 E2E 说明](../frontend/README.md#真实后端-e2e)。它复用本节的 PostgreSQL 配置、临时库与正式迁移设施，装配正式路由、异常处理和 `app.main.lifespan`，保留业务服务、Agent 图及 PostgreSQL checkpoint；启动器通过正式配置服务写入假密钥和默认模型，只在作用域内注入部署测试配置与模型 HTTP 边界，不增加生产环境测试开关。

模型替身提供普通多轮、真实天气工具调用，以及逐段交付后的等待和失败场景。浏览器 fixture 通过本次运行独立令牌访问测试专用控制路由，每个场景拥有独立门控；这些路由仅存在于测试装配应用中，服务只绑定回环地址。业务认证与聊天请求始终经过正式后端和临时数据库，不使用真实模型密钥。

启动器先构建前端，再创建随机库和启动服务。构建失败不建库，迁移失败沿用临时库上下文清理；启动和浏览器失败也先释放等待中的模型，关闭服务、连接与本次子进程，再删除当前运行创建的库。单元测试 `tests/unit/support/test_e2e.py` 覆盖门控、控制授权、启动失败、浏览器失败、退出码与清理顺序。强制终止进程可能无法执行 finally，终端会输出本次库名供核对；不自动扫描或删除其他运行留下的库。

模型配置浏览器项目在既有聊天项目完成后独占运行；测试装配为配置服务的主动模型测试复用本地供应商替身，并提供受运行令牌保护的配置重置路由。重置通过正式服务先清除默认、再删除模型和供应商，逐次使用读取版本，不修改生产路由或开发库；专项支撑回归位于 `tests/unit/support/test_e2e_model_configuration.py`。具体浏览器项目与选择命令统一见前端 E2E 说明。

CLI 子进程的标准输出和错误输出通过两条管道并发读取，再由 Python 实时转发，避免 Windows 隐藏控制台及多层脚本调用时丢失构建、Playwright 汇总和失败详情；退出码保持原样。结束或取消后先完成进程回收和输出读取，再退出命令。上述支撑测试覆盖成功与失败输出、无需文件句柄的捕获流、大量双路输出及取消清理。

### 覆盖的关键行为

标题专项单元测试覆盖规范化、严格类型、Unicode 长度、输入截断及关闭资源；PostgreSQL 专项 `test_conversation_titles.py` 与 `test_conversation_title_migration.py` 覆盖标题先于 done、问答历史隔离、失败/超时/取消重试、并发手动改名、角色隔离、排序、选择失效仍可改名、迁移往返与来源约束。供应商协议测试用五种正式客户端格式验证无工具标题调用；聊天 E2E 通过真实改名接口验证刷新及续聊后标题保留。

集成测试覆盖注册竞争、JWT 声明与账号状态、ORM 约束和索引、Alembic 排除 checkpoint 表、角色与部门范围、个人内容隔离、游标边界、公开工具历史、软删除、跨连接锁、取消清理、遗留状态恢复及最终提交失败。权限专项覆盖凭据撤销、最后超管保护、跨部门加入竞争、撤权后事务复查及历史身份迁移。模型仍使用本地替身，不访问真实模型。其他测试覆盖配置优先级、资源释放、接口协议、导入无外部副作用，以及真实 LangChain 图的多轮对话和工具调用；日志配置在独立子进程中验证。

受限模型选择专项位于 `tests/unit/llm/test_selection.py`、`tests/integration/postgres/test_model_selection.py` 和 `test_model_selection_migration.py`：覆盖固定/自选范围、预算边界、启停与默认、立即保存、版本竞争、所有权、执行锁、目录批量查询、配置失效、无效输入无副作用和迁移往返。已有供应商协议测试继续验证跨模型历史与凭据轮换兼容。

路由测试验证 `/api/chat` 的 SSE 事件、响应头、校验及流内错误、旧路径 `404`、错误方法 `405` 及 `Allow` 头、实例复用、依赖覆盖和 OpenAPI 示例。Agent 测试用可控异步事件验证首段先于完成、同会话 FIFO、跨会话并发、取消与异常后恢复、锁回收、最终落库边界，以及真实图取消时保留用户输入但不保存半段助手回复。

错误处理测试覆盖码值唯一性、业务码类型与范围、成功数据类型、业务失败 HTTP `200`、参数与协议错误、响应头保留、未知异常与响应模型校验失败，以及 CLI 退出码和异常日志不重复。另用短暂启动的本地 Uvicorn 服务验证兜底响应和实际堆栈输出，测试完成即关闭服务；该测试也不依赖模型或数据库。

SSE 专项测试另在临时回环端口启动本地 Uvicorn，使用真实 HTTP 客户端验证首段增量在生成完成前到达、流中失败和客户端断开取消；完成后关闭客户端、服务器与套接字。模拟 ASGI 2.0/2.4 覆盖排队、模型等待、发送失败和服务器取消时的异步清理；普通启动及 reload 配置均核对事件循环工厂。

过程事件测试使用真实图验证并行工具独立完成、命令类型标记、工具参数和结果、可恢复及不可恢复错误、执行前拒绝、artifact 排除及工具执行取消。模型适配测试通过 MockTransport 模拟 DeepSeek HTTP SSE，由正式客户端解析内部思考及工具参数碎片，验证推理不外发、缺少正文时的兜底顺序，并核验 checkpoint 和工具后续、多轮请求中的 reasoning_content 回传，不访问真实模型。

真实模型验收先注册登录，在首次 start 取得会话 ID，再于同一 `conversation_id` 告知姓名并追问姓名；省略 ID 创建另一会话确认历史隔离，重启服务后使用原标识继续对话。测试模型的实际回复不应作为固定文本断言。

## 目录职责

- `app/__main__.py`：统一 Web 启动入口，处理地址、端口、reload 参数并向 Uvicorn 传递日志配置。
- `app/main.py`：FastAPI 应用、启动/退出资源管理、全局异常处理器注册和 API 总路由挂载。
- `app/agents/`：Agent 专属实现；`models.py` 保留旧 DeepSeek 适配导入入口，`events.py` 适配工具生命周期，`prompts.py` 定义提示词，`tools/` 定义工具，`factory.py` 组装 Agent，`agent.py` 执行对话，`__main__.py` 提供命令行示例。
- `app/llm/`：供应商专用客户端、模型目录与参数策略、历史兼容、凭据加密和每轮执行装配；测试位于 `tests/unit/llm/` 及供应商协议集成测试。
- `app/core/`：Web、CLI 与其他后端模块共用的基础能力；`settings.py` 读取和校验配置，`logging.py` 集中配置标准日志，`event_loop.py` 创建兼容 Psycopg 的事件循环，`errors/` 维护错误码、应用异常和异常日志责任。
- `app/db/`：异步业务引擎、迁移版本校验、跨进程会话执行锁，以及独立管理的 checkpoint 资源。
- `app/schemas/`：认证、权限和聊天输入输出，以及通用响应模型；`identifiers.py` 集中维护用户名类型与规范化函数，供 HTTP 输入和本地运维共同复用。
- `app/api/`：API 总路由、公共请求依赖、按业务划分的子路由、SSE 编码与断开清理，以及统一异常处理器和错误响应文档；结构与扩展步骤见[分级 API 路由](#分级-api-路由)。
- `app/models/`：SQLAlchemy 业务实体。
- `app/repositories/`：无隐式提交的异步 ORM 读写，事务提交由业务服务负责。
- `app/services/files/`：共享文件业务入口及空间授权、目录分页、上传策略、传输和可靠清理；不将磁盘路径暴露给 API。
- `app/storage/`：私有原文件存储适配，当前为本地磁盘；不包含角色或空间权限规则。
- `app/services/`：认证、会话所有权、游标读取及轮次持久化；`conversation_titles.py` 独立承担无工具标题概括，超时和保存由会话服务编排；具体 SQL 查询交给仓储，HTTP/SSE 编码交给 API 层。
- `app/utils/`：预留不包含业务规则的通用辅助函数，当前尚无具体实现；游标、SSE 编码和数据库锁仍归属各自模块。
- `migrations/`：Alembic 异步环境和版本迁移，仅管理业务表。
- `tests/`：按单元与集成层级组织测试，共享支撑位于 `tests/support/`；归属、资源隔离和运行命令见[测试](#测试)。

后续开发外部服务接入时，再按需添加 `app/integrations/`。

`core` 不反向依赖 API、业务服务或具体 Agent；各入口显式调用配置和日志初始化函数，导入核心模块不会连接数据库或调用模型。HTTP 异常响应转换仍由 `app/api/exception_handlers.py` 负责。新增代码优先放在职责明确的模块中，不因被多个位置调用就移入 `core` 或 `utils`。

接口和智能体工具应复用业务服务，由服务执行文件访问与知识检索的权限校验。

项目使用平铺的 `app/` 包布局，已在 `pyproject.toml` 中显式配置 uv 的包发现路径。
