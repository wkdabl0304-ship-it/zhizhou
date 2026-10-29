# 共享文件接口与存储

本模块提供原文件管理后端，尚未实现文件管理页面、聊天附件、预览、解析、RAG、文件移动、版本历史或回收站。Swagger 为 `/docs`，业务路径统一以 `/api/files` 开头。运行环境与数据库准备见[后端 README](../README.md)。

## 权限及上传限制

所有接口使用 `Authorization: Bearer <access_token>`。每次请求查询当前账号及授权，JWT 不保存权限。全员可读全局空间，部门成员可读本部门空间；超管管理所有共享空间，部门管理员管理本部门，本人管理个人空间。超级管理员也不能读取他人个人内容。

文件维护使用 `file:read / upload / update / delete`，新建目录使用上传权限；普通用户的 self 授权只覆盖本人个人空间。默认共享读取由文件服务明确判断，不把普通用户授予为全局文件读取者。`global` 文件授权仅覆盖共享空间，个人空间还必须满足本人归属。

允许任意格式及零字节文件，原件只作为附件下载，不解析或执行。初始单文件上限为 `104857600` 字节（100 MiB）。全局空间一个策略、个人空间共用一个策略、每个部门单独一个策略。超管维护全部策略，部门管理员只维护本部门。配置允许严格整数 `1..1099511627776`（1 字节至 1 TiB）。不提供总容量配额。

## 空间与目录 API

普通成功响应为 `{code:0,message:"成功",data:...}`。错误为 `{code,message,data:null}`。UUID 均由后端生成；所有输入对象拒绝未知字段。

| 方法与路径（省略 `/api/files`） | 输入 | 成功 data |
| --- | --- | --- |
| `GET /spaces` | `limit=20&cursor=...` | `{items:SpaceInfo[],next_cursor}` |
| `GET /spaces/{space_id}` | 无 | `SpaceInfo` |
| `GET /spaces/{space_id}/entries` | `parent_id?&limit=20&cursor=...` | `{space,parent_id,breadcrumbs,items:EntryInfo[],next_cursor}` |
| `GET /entries/{entry_id}` | 无 | `{entry:EntryInfo,breadcrumbs}` |
| `POST /spaces/{space_id}/folders` | `{name,parent_id?:null}` | `EntryInfo` |
| `POST /spaces/{space_id}/files` | 可选查询 `parent_id`；multipart 仅一个 `file` | `EntryInfo`，名称可能自动加序号 |
| `PATCH /entries/{entry_id}` | `{name,version}` | 修改后的 `EntryInfo` |
| `DELETE /entries/{entry_id}` | 必填查询 `version` | `null` |
| `GET /entries/{entry_id}/download` | 无 | 完整二进制附件 |

`SpaceInfo` 包含 `id / kind / name / department_id / owner_id / max_file_size_bytes / capabilities`。`kind` 为 `global / department / personal`。`capabilities` 为允许操作数组，元素为 `read / upload / update / delete`。非部门空间的 `department_id` 为 null，非个人空间的 `owner_id` 为 null。

`EntryInfo` 包含 `id / space_id / parent_id / kind / name / size_bytes / created_by / version / created_at / updated_at`。`kind` 为 `file / folder`。根目录内条目的 `parent_id` 为 null；目录的大小为 null，空文件为 0。`created_by` 记录来源，不授予共享内容维护权。时间使用带时区 ISO 8601，所有公开对象均不包含原件键和已删除状态。

面包屑为从根向下的 `{id,name}` 数组，空间本身表示根目录。目录详情包含目录自身，文件详情包含其父目录链。根目录为虚拟节点，不能重命名或删除；不支持下载目录压缩包。

分页按 `(created_at DESC,id DESC)`，`limit` 为 1–100，无下一页时 `next_cursor=null`。游标绑定操作者、当前部门和授权、空间及父目录，不能跨目标复用；授权或部门改变后旧游标可能返回 422。分页是实时视图，不承诺跨请求快照。

名称去除首尾空白并做 NFC 规范化，长度为 1–255 个 Unicode 字符，拒绝 `.`、`..`、路径分隔符及控制字符。同目录用 NFC + casefold 判重，文件和目录共用名称。新建目录和改名冲突返回 409；上传按最小可用序号另存，例如 `方案.pdf` → `方案 (1).pdf`。最后扩展名尽量保留，必要时截短主名；极长扩展名无法保留时截短整体名称再追加序号。不比较内容、不覆盖既有文件。

重命名和删除必须携带读取到的正整数版本。名称实质不变时返回当前对象，不递增版本；仅修改大小写会保存并递增版本。已删除条目再操作返回 404。上传没有幂等键，重复提交会形成另一份文件；调用方不能盲目自动重试。

上传示例（PowerShell 使用 `curl.exe`）：

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/files/spaces/<空间UUID>/files?parent_id=<目录UUID>" `
  -H "Authorization: Bearer <access_token>" -F "file=@D:/资料/方案.pdf"
```

上传在解析请求体前鉴权。实际文件数据逐块计数，不信任 Content-Length；仅接受一个文件、零个普通字段，并限制 multipart 头及边界额外开销。表单临时文件无论成功、失败或取消均关闭。完成落盘后重新检查当前账号、权限、有效父目录及最新大小策略，通过后才发布到目录。期间降低上限可能让尚未发布的上传失败，已保存文件不受影响。

下载成功使用 `application/octet-stream`、UTF-8 附件名称、实际 Content-Length、`Cache-Control: private, no-store` 和 `X-Content-Type-Options: nosniff`。首版忽略 Range，发送完整附件。原件不会挂载到静态 URL。发送开始前的失败仍返回统一 JSON；发送开始后的传输故障只能中断连接，调用方需检查传输是否完整。

## 上传策略 API

| 方法与路径（省略 `/api/files`） | GET 可见范围 | PATCH 权限 |
| --- | --- | --- |
| `GET/PATCH /upload-limits/global` | 所有登录账号 | 全局管理授权 |
| `GET/PATCH /upload-limits/personal` | 所有登录账号 | 全局管理授权 |
| `GET/PATCH /upload-limits/departments/{department_id}` | 本部门成员、全局文件读取授权 | 对应部门或全局管理授权 |

PATCH 输入为 `{"max_file_size_bytes":209715200,"version":1}`。大小及版本只接受整数，布尔、字符串和未知字段均拒绝。GET/PATCH 返回：

```json
{
  "code": 0,
  "message": "成功",
  "data": {
    "scope_type": "department",
    "department_id": "<部门UUID>",
    "max_file_size_bytes": 209715200,
    "version": 2,
    "updated_by": "<修改人UUID>",
    "updated_at": "<带时区时间>"
  }
}
```

全局及个人策略的 `department_id` 为 null，初始化尚未人工修改时 `updated_by` 为 null。写入相同上限不递增版本；旧版本仍返回冲突。策略修改和上传发布锁定同一策略行，按实际事务提交顺序生效。

## 错误

| HTTP / code | 含义 |
| --- | --- |
| 401 / `40101`、`40103` | 登录无效、凭据已撤销或账号停用 |
| 403 / `40301` | 可以读取目标但没有请求的维护权限 |
| 404 / `40406` | 空间不存在、已关闭或不可见 |
| 404 / `40407` | 条目不存在、已删除、父目录不可用或目标不可见 |
| 404 / `40405` | 查询部门策略时部门不存在或不可见 |
| 409 / `40909` | 同目录名称冲突 |
| 409 / `40910` | 条目版本冲突 |
| 409 / `40911` | 上传策略版本冲突 |
| 413 / `41301` | 文件或请求传输超过受限大小 |
| 422 / `42200` | UUID、名称、版本、上限、游标或 multipart 输入不合法；例如向文件节点下上传或下载目录 |
| 500 / `50004` | 原件缺失、磁盘不可写或其他存储故障 |

不存在和不可见的条目使用相同响应，不泄露他人个人文件；服务器路径不会出现在错误消息中。

## 数据字典

以下字段除标明可 NULL 外均非空，UUID 主键由后端生成，时间为 TIMESTAMPTZ。完整约束见 [ORM](../app/models/files.py) 及冻结的[正式迁移](../migrations/versions/0007_file_spaces.py)。

### file_spaces

| 字段 | 类型及默认值 | 含义和取值 |
| --- | --- | --- |
| id | UUID PK，UUIDv4 | 空间标识 |
| kind | VARCHAR(16)，无默认 | global 全局、department 部门、personal 个人 |
| department_id | UUID FK，可 NULL | 有效部门空间必须关联部门；非部门空间为 NULL，部门删除后关闭空间的关联置 NULL |
| owner_id | UUID FK RESTRICT，可 NULL | 个人空间必须关联本人；非个人为 NULL |
| created_at | TIMESTAMPTZ，now | 空间创建时间 |
| deleted_at | TIMESTAMPTZ，可 NULL，默认 NULL | NULL 有效；非空为部门关闭时间，无恢复入口 |

有效全局空间、每个部门空间和每人个人空间分别唯一。空间类型与归属受 CHECK 限制。部门外键 SET NULL 之前必须先关闭空间。

### file_upload_policies

| 字段 | 类型及默认值 | 含义和取值 |
| --- | --- | --- |
| id | UUID PK，UUIDv4 | 策略内部标识 |
| scope_type | VARCHAR(16)，无默认 | global 全局、personal 个人统一、department 部门独立 |
| department_id | UUID FK CASCADE，可 NULL | 部门策略必须填写；其他为 NULL；部门删除时清除此策略 |
| max_file_size_bytes | BIGINT，104857600 | 单文件字节上限，范围 1–1099511627776 |
| version | INTEGER，1 | 正整数并发版本，实际修改后递增 |
| updated_by | UUID FK RESTRICT，可 NULL | 最后修改人；NULL 表示迁移或初始化后尚未修改 |
| created_at | TIMESTAMPTZ，now | 策略创建时间 |
| updated_at | TIMESTAMPTZ，now | 最后修改时间 |

全局、个人策略各唯一，部门策略按部门唯一。类型与部门组合、大小和版本由 CHECK 约束。

### file_blobs

| 字段 | 类型及默认值 | 含义和取值 |
| --- | --- | --- |
| id | UUID PK，UUIDv4 | 原件标识，也是跨进程锁对象 |
| storage_key | VARCHAR(100)，唯一，无默认 | 后端生成的 `ab/<UUID十六进制>.blob`，不含显示名称、不对外返回 |
| state | VARCHAR(16)，staging | staging 尚未发布；ready 已发布；delete_pending 待清理；purged 磁盘已清理 |
| size_bytes | BIGINT，可 NULL | 非负实际字节数；未完成时 NULL，完成后保留，空文件为 0 |
| sha256 | CHAR(64)，可 NULL | 完成后的 64 位小写十六进制摘要；未完成时 NULL，清理后保留已知值 |
| created_at | TIMESTAMPTZ，now | 原件登记时间 |
| updated_at | TIMESTAMPTZ，now | 生命周期状态最后变化时间 |

ready 必须具有大小和合法摘要。按 state 索引扫描清理。清理后的元数据墓碑保留，不支持恢复或自动按内容去重。

### file_entries

| 字段 | 类型及默认值 | 含义和取值 |
| --- | --- | --- |
| id | UUID PK，UUIDv4 | 用户可见条目标识 |
| space_id | UUID FK RESTRICT，无默认 | 所属空间 |
| parent_id | UUID，可 NULL | 同空间父目录；NULL 表示根目录；不能指向自身 |
| kind | VARCHAR(16)，无默认 | file 文件、folder 目录 |
| name | VARCHAR(255)，无默认 | 规范化显示名称，1–255 字符 |
| name_key | TEXT，无默认 | NFC + casefold 比较键，不对外返回 |
| blob_id | UUID FK RESTRICT，唯一，可 NULL | 文件必须关联唯一原件；目录必须为 NULL |
| created_by | UUID FK RESTRICT，无默认 | 创建人，只记录来源 |
| version | INTEGER，1 | 正整数版本，重命名或删除时递增 |
| created_at | TIMESTAMPTZ，now | 目录创建或文件发布时刻 |
| updated_at | TIMESTAMPTZ，now | 最近条目修改时间 |
| deleted_at | TIMESTAMPTZ，可 NULL，默认 NULL | NULL 有效；非空为逻辑删除时间，无恢复入口 |

复合父外键 `(space_id,parent_id)` 保证同空间关联。有效 `(space_id,parent_id,name_key)` 唯一，使用 PostgreSQL 16 的 NULLS NOT DISTINCT 保证根目录也判重；删除后名称可复用。另有父子查询及有效目录分页索引。

## 事务、清理与运维

升级执行 `uv run alembic upgrade head`。`0007_file_spaces` 为已有账号和部门创建空空间，为共享范围创建默认策略并补齐角色文件授权。以后注册账号及创建部门均在同一主体事务创建空间。删除部门会在同一事务关闭其空间、递归删除资料、标记原件待清理，再解除成员关系、角色和部门策略；个人资料保留。

短事务按管理共享锁 → 空间读写锁的顺序执行。管理撤权和部门删除使用已有管理独占锁；目录写入在同空间串行化，读取持空间共享锁，避免看到部分递归删除。上传和下载传输期间不持数据库事务，但分别通过独立连接持有原件独占锁和共享锁。

原件先登记 staging，在同一存储目录写 `.part`，同步文件内容后原子重命名。完成数据库发布后才变为 ready。失败尽快回收；即使进程中断，staging 仍可恢复清理。删除立即隐藏条目并设为 delete_pending。启动扫描及每 60 秒扫描会尝试取得原件独占锁，跳过进行中的传输，清理成功变为 purged；磁盘删除或数据库提交失败会保留状态供重试。

已开始的下载可读完，后续下载请求按最新删除、账号和权限状态判断。清理只能在最后一个下载释放共享锁后执行。下载断开及服务退出都会关闭句柄和锁连接，周期任务在数据库关闭前停止。

`FILE_STORAGE_ROOT` 默认为后端 `.data/files`，相对路径基于 backend，而不是启动目录；启动时验证目录可写。多进程或多个实例必须共用同一目录和数据库，本实现不支持各实例各存一份本地磁盘。数据目录不对外静态发布，并已加入根忽略规则。

备份应同时覆盖 PostgreSQL、原件目录及模型凭据主密钥；取得一致备份时暂停业务写入和文件清理，随后共同备份数据库及磁盘，恢复时成对还原。只恢复数据库可能出现元数据指向缺失原件。迁移不会替运维清理磁盘；存在任何条目或原件记录时，破坏性降级会被拒绝，需先备份并明确清理业务数据。

测试命令和随机库、临时文件隔离规则见[后端测试](../README.md#测试)。
