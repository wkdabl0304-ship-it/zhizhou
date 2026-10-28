# 权限、用户与部门：后端设计和前端对接

本文维护首期权限模块的数据模型、业务边界与 HTTP 契约。字段及错误的可执行定义以正式 OpenAPI、schema 和中央错误码为准；部署、测试入口仍见[后端 README](../README.md)。

## 角色与范围

所有账号都绑定 `user` 基础角色，可叠加 `department_admin`、`super_admin`。业务服务检查操作权限和资源范围，不使用角色名决定是否允许操作。内置角色和权限由迁移维护，暂不开放自定义角色接口。

| 角色 | 绑定位置 | 授权 |
| --- | --- | --- |
| `user` | 账号级，不绑定部门 | `model:use@global`；五项会话操作 `conversation:create/read/update/delete/chat@self` |
| `department_admin` | 某个具体部门 | `department:read@department`；`department_member:read/add/remove@department` |
| `super_admin` | 账号级，不绑定部门 | `model:manage`、`user:read/set_active/reset_password`、`department:read/create/update/delete`、`department_member:read/add/remove`、`role:assign/revoke`，均为 `global` |

表格斜线仅用于缩写，数据库逐项保存完整权限代码，没有通配符或角色继承。

`global` 只覆盖同一个操作的资源范围，不会匹配其他操作。管理员没有个人会话的全局读写权限。会话查询还在 SQL 层限定所有者；其他人的会话统一返回 `40401`。文件尚未实现，未来文件入口也须接入相同边界。

部门管理员必须属于所管理部门；失配的绑定即使残留在数据库也不会生效。管理员可以移除本人，成功后失去部门权限。超管可以属于一个部门，离开或删除部门不会撤销其全局授权。

普通成员不能查看全站账号目录；部门管理员只能按完整用户名加入已有、启用、无部门的账号。立即加入，不产生待确认邀请或消息。已经在目标部门时重复加入成功；属于其他部门则必须先移除再加入。

## 数据库逐字段说明

业务迁移版本为 `0006_authorization`。UUID 由后端生成，内置角色和操作 ID 由迁移生成稳定 UUID；所有时间列为 `TIMESTAMPTZ`，创建时间默认数据库 `now()`，更新时间由 ORM 写入时维护。除明确可空的字段外均非空；未注明数据库默认值的字段由服务或迁移显式填写。只有注明可空的字段允许 NULL，其业务含义见对应行；空字符串不作为无归属或无范围的表示方式，部门名称和用户名按各自输入规则拒绝空白。

### users：账号与当前归属

| 字段 | 类型与约束 | 用途 |
| --- | --- | --- |
| `id` | UUID，主键 | 稳定账号 ID，会话和角色绑定引用它 |
| `username` | VARCHAR(32)，唯一 | 登录和精确加入成员；标准化为去首尾空白的小写，3～32 位 ASCII 字母、数字或下划线 |
| `password_hash` | TEXT | 带盐 Argon2 密码摘要，不返回给前端；重置密码替换该值 |
| `is_active` | BOOLEAN，默认 true | true 表示启用，false 表示停用；停用禁止登录和后续认证，但保留归属、角色、个人数据 |
| `department_id` | UUID，可空，外键 departments.id，索引 | 当前唯一部门；NULL 表示无部门；RESTRICT 防止绕过业务流程直接删部门 |
| `token_version` | INTEGER，默认 1，CHECK > 0 | 当前有效凭据版本；与 JWT 中同名整数比较，停用或改密递增 |
| `created_at` | TIMESTAMPTZ，默认 now() | 账号创建时间，也是用户及成员列表分页排序时间 |
| `updated_at` | TIMESTAMPTZ，默认 now() | 此账号记录最近修改时间，不表示完整审计历史 |

旧 `role` 列已移除，唯一授权事实来自 RBAC 表。单部门通过一个可空外键表达，暂不另建成员关系和成员历史表。

### departments：部门资料

| 字段 | 类型与约束 | 用途 |
| --- | --- | --- |
| `id` | UUID，主键 | 部门稳定 ID，改名不会影响归属和授权 |
| `name` | VARCHAR(100)，唯一，去空白后非空 | 部门显示名，按标准化后的完整值判重；数据库也检查空白边界 |
| `created_at` | TIMESTAMPTZ，默认 now() | 创建时间、部门列表排序时间 |
| `updated_at` | TIMESTAMPTZ，默认 now() | 部门名称最近修改时间；成员进出不修改它 |

不保存管理员数组、成员数组或冗余人数。第一版无部门树和软删除；删除先撤销部门绑定、解除所有成员归属，再硬删除部门，账号及个人内容保留。

### roles：角色定义

| 字段 | 类型与约束 | 用途 |
| --- | --- | --- |
| `id` | UUID，主键 | 角色内部 ID，关联用户绑定及权限模板 |
| `code` | VARCHAR(64)，唯一 | 稳定机器代码，如 department_admin；用于生命周期配置与展示，不用于业务鉴权分支 |
| `name` | VARCHAR(100) | 中文显示名，修改不影响授权 |
| `binding_scope` | VARCHAR(20)，CHECK global/department，无默认值 | `global` 表示账号级绑定，绑定记录的 department_id 必须为 NULL；`department` 表示具体部门绑定，department_id 必须匹配用户当前部门。此字段说明绑定位置，不代表操作可访问全部资源 |

`user` 和 `super_admin` 为账号级绑定，`department_admin` 为部门级绑定。账号级角色可以同时包含全局操作和本人操作，因此 `user.binding_scope=global` 不意味着可以看全站会话。

### permissions：操作目录

| 字段 | 类型与约束 | 用途 |
| --- | --- | --- |
| `id` | UUID，主键 | 操作内部 ID，角色授权模板引用它 |
| `code` | VARCHAR(100)，唯一 | 服务检查的具体操作，如 department_member:add |
| `name` | VARCHAR(100) | 操作中文说明 |

角色和操作首期均由迁移维护，不保存编辑版本、创建人或编辑时间。`user:read` 仅表示账号管理资料，不包含该用户的个人资源或凭据。

### role_permissions：角色授权模板

| 字段 | 类型与约束 | 用途 |
| --- | --- | --- |
| `role_id` | UUID，外键 roles.id | 此项授权属于哪个角色 |
| `permission_id` | UUID，外键 permissions.id | 授予哪个具体操作 |
| `scope_type` | VARCHAR(20)，CHECK global/department/self | 此操作允许覆盖的资源范围 |

三字段为联合主键，防止重复授权。`global` 覆盖该操作的所有资源；`department` 要求目标部门匹配绑定部门，且操作者仍在该部门；`self` 要求资源所有者是当前用户。模板不存具体部门或用户 UUID，解析时分别从角色绑定和认证身份取得。

### user_roles：当前用户角色绑定

| 字段 | 类型与约束 | 用途 |
| --- | --- | --- |
| `id` | UUID，主键 | 此次绑定的独立记录 ID |
| `user_id` | UUID，外键 users.id，索引 | 谁获得角色 |
| `role_id` | UUID，外键 roles.id | 获得哪种角色 |
| `department_id` | UUID，可空，外键 departments.id，索引 | 部门角色在哪个部门有效；账号级角色为 NULL |
| `created_at` | TIMESTAMPTZ，默认 now() | 当前这次绑定创建时间，撤销再授予会产生新记录 |

部分唯一索引分别约束账号级 `(user_id,role_id)` 和部门级 `(user_id,role_id,department_id)`。外键检查引用存在性；事务服务检查角色绑定位置及用户归属一致性；鉴权查询再次过滤错误绑定。

`users.department_id` 是成员归属，`user_roles.department_id` 是管理授权位置。撤销部门管理员只删除绑定，不让用户离开部门；移除成员会撤销该部门全部绑定，然后解除归属。基础角色不能通过管理接口撤销。

不做临时或历史授权，因此没有 expires_at、revoked_at 或绑定 is_active。撤销直接删除当前绑定，历史变化以后由独立审计模块记录。

### 示例

张三的 users.department_id 为研发部 D1。user_roles 有两行：账号级 user 绑定、D1 的 department_admin 绑定。部门管理员模板提供 department_member:add@department，因此他只能向 D1 加人；基础角色提供 conversation:read@self，因此他只能读取自己的会话。任命为超管后仍不会得到他人会话的读取权限。

## 认证协议与前端授权

所有 JSON 接口使用 `{code,message,data}`；成功 code 为 0，失败 data 为 null。注册登录外均要求 `Authorization: Bearer <token>`。

| 方法和路径 | 输入 | 结果 |
| --- | --- | --- |
| POST /api/auth/register | username、password，可选 role:"user" | 公开身份加 created_at；只创建普通用户，提交管理角色 422 |
| POST /api/auth/login | username、password | access_token、token_type:"bearer"、expires_in、user |
| GET /api/auth/me | 无 | 最新本人身份、部门、角色及有效授权 |

公开身份形状如下，grants 为节选，实际返回完整有效授权：

```json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "username": "zhangsan",
  "role": "user",
  "department": {"id": "22222222-2222-4222-8222-222222222222", "name": "研发部"},
  "roles": ["department_admin", "user"],
  "grants": [
    {"permission": "department_member:add", "scope_type": "department", "scope_id": "22222222-2222-4222-8222-222222222222"},
    {"permission": "conversation:read", "scope_type": "self", "scope_id": "11111111-1111-4111-8111-111111111111"}
  ]
}
```

| 字段 | 含义 |
| --- | --- |
| id / username | 账号标识和登录名 |
| role | 临时兼容的 user/super_admin 展示字段；部门管理员仍显示 user，禁止据此授权 |
| department | 当前部门的 id/name；无部门时 null |
| roles | 有效角色代码数组，可同时包含基础角色和多个管理角色 |
| grants[].permission | 具体操作代码 |
| grants[].scope_type | global、department 或 self |
| grants[].scope_id | global 为 null，department 为部门 ID，self 为本人 ID |

前端登录后用 user.grants 控制入口，刷新用 /auth/me 重新确认。判断部门操作时必须同时匹配操作代码及范围 ID；角色名称仅用于展示。后端独立复查，隐藏按钮不能代替鉴权。

401 时清除当前登录并引导重新登录；403 时刷新身份、反馈权限变化；409 时刷新目标资料。当前前端产品代码尚未接入 grants，可能仍显示模型管理入口，普通用户调用管理接口会得到 403。

JWT 只携带身份、签发/过期约束和 token_version，不保存角色或权限快照。停用及改密递增版本，再启用不恢复旧令牌。角色、部门变更不要求重新登录，后续请求读取最新授权。已经开始的流式生成允许完成，不实施实时强制中断。

## 用户管理接口

| 方法和路径 | 请求 | 响应 data | 权限 |
| --- | --- | --- | --- |
| GET /api/users | search、is_active、department_id、unassigned、limit、cursor | 管理账号分页 | user:read@global |
| GET /api/users/{user_id} | 无 | 管理账号 | user:read@global |
| PUT /api/users/{user_id}/active | {"is_active":false} | 更新后的管理账号 | user:set_active@global |
| PUT /api/users/{user_id}/password | {"password":"new-password"} | null | user:reset_password@global |
| PUT /api/users/{user_id}/super-admin | 无 | null | role:assign@global |
| DELETE /api/users/{user_id}/super-admin | 无 | null | role:revoke@global |

管理账号字段为 id、username、is_active、department、roles、created_at、updated_at。department 为 id/name 或 null，roles 为有效角色代码数组。不会返回密码哈希、令牌版本、JWT 或个人会话。

search 在规范化用户名内做子串匹配，百分号和下划线按字面搜索。department_id 与 unassigned=true 不能同时使用。密码保留原空格，长度 8～128，不出现在 repr 或响应中。

重置密码直接设置新密码并撤销全部旧令牌，不改变启停。能设置密码的管理员可能以该账号登录；管理员身份本身仍不具备个人内容访问权。

超管授予要求目标启用，重复授予和撤销幂等。停用或撤销最后一名可用超管返回 40906；允许管理本人，但同样执行此约束。超管身份不依赖部门。

## 部门与成员接口

| 方法和路径 | 请求 | 响应 data | 权限 |
| --- | --- | --- | --- |
| GET /api/departments | limit、cursor | 可见部门分页 | department:read，按范围过滤 |
| POST /api/departments | {"name":"研发部"} | 部门 | department:create@global |
| GET /api/departments/{id} | 无 | 部门 | department:read，匹配目标部门 |
| PATCH /api/departments/{id} | {"name":"新名称"} | 部门 | department:update@global |
| DELETE /api/departments/{id} | 无 | null | department:delete@global |
| GET /api/departments/{id}/members | search、limit、cursor | 部门成员分页 | department_member:read，匹配部门 |
| POST /api/departments/{id}/members | {"username":"zhangsan"} | 部门成员 | department_member:add，匹配部门 |
| DELETE /api/departments/{id}/members/{user_id} | 无 | null | department_member:remove，匹配部门 |
| PUT /api/departments/{id}/administrators/{user_id} | 无 | null | role:assign@global |
| DELETE /api/departments/{id}/administrators/{user_id} | 无 | null | role:revoke@global |

部门字段为 id、name、created_at、updated_at。成员字段为 id、username、is_active、roles；这里 roles 只包含当前部门角色，普通成员为空数组，不公开全局管理员身份。

加入必须使用完整用户名；已在本部门时重复加入成功，其他部门 40905，停用账号 40907。移除已无部门账号成功，账号已在别的部门则 40907。任命要求目标为本部门启用成员；重复撤销幂等，撤销不改变成员归属。

删除部门在同一事务撤销所有部门授权、解除全部成员归属、删除部门。保留全局角色、账号、会话及 checkpoint。事务任何一步失败整体回滚。

建议调用顺序：超管创建部门 → 按用户名加入成员 → 任命管理员；部门管理员读取本部门和成员 → 按完整用户名加入或移除；跨部门调整先从原部门移除，再加入目标部门，原管理角色不会自动带入新部门。

### 分页

三个列表均使用 limit/cursor，默认 20、最大 100，按创建时间和 UUID 降序，返回：

```json
{"code": 0, "message": "成功", "data": {"items": [], "next_cursor": null}}
```

成员排序时间为账号创建时间，不是加入部门时间。下一页原样传回 next_cursor，不改变筛选。游标绑定操作者、接口、筛选及当前授权；跨用户、跨筛选或授权变化后复用返回 42200，前端应从第一页刷新。没有 offset 或页码。

## 现有模型与会话接口

GET /api/model-config/options 要求 model:use，普通用户可读取安全选项。其余 /api/model-config 接口，包括内置目录、连接/方案读取、修改、默认及主动测试，要求 model:manage@global。

模型对外管理入口为 ModelManagementService，内部 ModelConfigService 维护配置存储和运行时快照，只供已授权服务、可信初始化及测试装配使用。授权与配置读写共用一个 Session 和事务；底层借用事务不自行提交或关闭，避免持锁时申请第二个连接造成池耗尽。未来工具应复用已授权入口，不能直接暴露内部存储服务。

会话服务在业务入口检查对应 self 权限，并保留原所有者查询。首轮要求 conversation:create、conversation:chat、model:use；续聊要求后两项。读取要求 conversation:read，标题及选择修改要求 conversation:update，删除要求 conversation:delete。

## 错误、并发和运维

| HTTP / code | 含义 |
| --- | --- |
| 401 / 40101 | 凭据缺失、过期、版本失效或账号停用 |
| 401 / 40102 | 用户名或密码错误，停用登录也使用该错误 |
| 403 / 40301 | 缺少对应操作或范围权限 |
| 404 / 40401 | 会话不存在、删除或属于别人 |
| 404 / 40404 | 授权允许定位的目标账号不存在 |
| 404 / 40405 | 部门不存在或查询范围不可见 |
| 409 / 40905 | 账号已属于其他部门 |
| 409 / 40906 | 必须保留至少一名可用超管 |
| 409 / 40907 | 启停或归属不满足要求，刷新后重试 |
| 409 / 40908 | 部门名称重复 |
| 422 / 42200 | 请求字段、类型、筛选或游标无效 |

错误示例：

```json
{"code": 40301, "message": "没有执行此操作的权限", "data": null}
```

管理写入共用 PostgreSQL 事务级独占 advisory lock；管理读取用共享锁。取得锁后重查账号、凭据版本和授权。第一版选择简单可验证的短事务串行化，避免并发加入两个部门、删除残留、撤权后继续写入和最后超管丢失。会话短写事务用共享管理锁，模型生成与外部主动测试不持管理锁。

在 backend 目录执行：

```powershell
uv run alembic upgrade head
uv run python -m app.manage grant-super-admin zhangsan
```

先通过正式注册创建账号，再由有数据库运维权限的人执行本地命令。目标必须启用，命令可重复执行。没有公开初始化超管接口。无可用超管时用该命令恢复管理能力。

迁移保留旧账号、密码、启停和个人内容，全部绑定基础角色，并按已确认的兼容策略保留旧 super_admin 身份。旧 JWT 缺少版本声明，需要重新登录。降级恢复旧单角色，无法保存部门及部门授权，降级前备份。应用不会自动迁移开发或生产数据库。

## 测试与后续扩展

权限集成测试使用随机临时 PostgreSQL 库，覆盖角色范围、个人隐私、账号生命周期、分页、事务及并发保护。迁移测试检查旧身份与私人正文保留；模型管理 E2E 先公开注册，再通过仅测试装配存在且受本次随机控制令牌保护的通道授予超管。普通聊天 fixture 仍是普通用户。

以后自定义角色可增加目录编辑接口；部门资源保存明确的部门归属；多人分享通过独立资源授权关系接入统一授权服务；审计使用独立历史表。本期未创建这些预留业务表，也未实现实时中断既有流式生成。
