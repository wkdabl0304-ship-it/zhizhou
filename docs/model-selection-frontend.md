# 受限模型选择：前端对接文档

本文对应后端迁移 `0004_model_selection`。前后端已接通连接/模型启停、受限推理策略、聊天选项和会话选择，包含页面、状态管理及自动化测试。先在 `backend/` 执行 `uv run alembic upgrade head`，再启动对应版本后端。

管理配置的完整环境与接口说明见[后端文档](../backend/README.md#模型配置接口与两层适配)。本文集中说明前端如何对接新增能力，示例 UUID 需替换为实际接口返回值。

## 1. 需要区分的三类数据

| 数据 | 来源 | 前端用途 |
| --- | --- | --- |
| 原生模型目录 | `GET /api/model-config/catalog/models` | 管理页面编辑方案时判断模型能力 |
| 聊天允许范围 | `GET /api/model-config/options` | 聊天选择控件的唯一选项来源 |
| 会话当前选择 | 会话列表、详情及 SSE `start` | 恢复会话选择，检查保存版本及失效状态 |

所有登录用户仍可管理共享配置。连接是否启用、方案是否启用，以及原生能力是否有效，共同决定聊天可选性。不能直接将完整模型目录当作聊天允许范围。

全局默认只初始化尚无选择的会话。清除或切换全局默认不会更换已有会话的选择。用户明确选中有效方案后，无全局默认也能聊天。

## 2. 通用请求和类型

所有业务接口要求 `Authorization: Bearer <access_token>`。普通响应为 `{code,message,data}`，成功 `code=0`，失败 `data=null`。必须同时检查 HTTP 状态及 `code`；禁止把未知字段混入请求。模型密钥和地址不进入聊天选项或选择请求。

```ts
// 聊天只接受具体推理值，管理页面仍可使用模型目录 default。
type ConcreteReasoning =
  | { mode: 'off' }
  | { mode: 'effort'; effort: string }
  | { mode: 'budget'; budget_tokens: number }

type ModelSelection = {
  model_configuration_id: string
  reasoning: ConcreteReasoning
}

type SelectablePolicy = {
  mode: 'selectable'
  allowed_modes: Array<'off' | 'effort' | 'budget'>
  effort_options: string[]
  budget: { min: number; max: number } | null
}

type ReasoningPolicy = { mode: 'fixed' } | SelectablePolicy

type ReasoningControl =
  | { mode: 'fixed'; default: ConcreteReasoning }
  | (SelectablePolicy & { default: ConcreteReasoning })

type SelectionIssue =
  | 'model_deleted'
  | 'provider_disabled'
  | 'model_disabled'
  | 'model_unavailable'
  | 'reasoning_not_allowed'

type ConversationSelectionFields = {
  model_selection: ModelSelection | null
  model_selection_version: number
  model_selection_issue: SelectionIssue | null
}
```

`budget_tokens` 必须是整数；预算上下界是闭区间。`effort` 原样使用后端返回值，不维护跨模型统一枚举，也不按名称推测档位顺序。

## 3. 聊天可选范围

```http
GET /api/model-config/options
```

响应示例：

```json
{
  "code": 0,
  "message": "成功",
  "data": {
    "default_selection": {
      "model_configuration_id": "22222222-2222-4222-8222-222222222222",
      "reasoning": {"mode": "effort", "effort": "high"}
    },
    "providers": [
      {
        "provider_configuration_id": "11111111-1111-4111-8111-111111111111",
        "name": "DeepSeek 主账号",
        "provider": "deepseek",
        "models": [
          {
            "model_configuration_id": "22222222-2222-4222-8222-222222222222",
            "name": "日常问答",
            "catalog_model_id": "deepseek:deepseek-flash",
            "display_name": "DeepSeek Flash",
            "reasoning_control": {
              "mode": "selectable",
              "default": {"mode": "effort", "effort": "high"},
              "allowed_modes": ["off", "effort"],
              "effort_options": ["low", "high"],
              "budget": null
            }
          }
        ]
      }
    ]
  }
}
```

- 供应商按**连接 ID**分组，同品牌可以有多个连接。同一原生模型也可以有多个独立方案。
- 固定策略只有 `mode=fixed` 和具体 `default`，展示该值，不提供可编辑推理控件；发送时仍携带该具体值。
- 自选策略只展示 `allowed_modes`，档位只能取 `effort_options`，预算使用返回的 `min/max`。预算和档位是不同方式，不能同时发送。
- 选中新方案时，将其 `default` 复制为独立草稿，不能直接修改选项缓存。
- `default_selection=null` 表示没有有效默认，不等于没有可选模型。此时要求手动选择；`providers=[]` 才表示没有任何可选方案。
- 接口已经过滤停用和不可用配置，不返回端点、凭据或可覆盖的输出上限。范围已验证符合模型与输出上限，后端不会静默裁剪非法配置。

## 4. 新会话发送与确认

新会话尚无服务端 ID：切换选择只保留页面草稿，在首条消息中一起发送。

```http
POST /api/chat
Content-Type: application/json
```

```json
{
  "message": "帮我解释这个问题",
  "model_selection": {
    "model_configuration_id": "22222222-2222-4222-8222-222222222222",
    "reasoning": {"mode": "effort", "effort": "low"}
  }
}
```

省略 `model_selection` 或传 `null` 时使用有效全局默认。推荐界面明确显示默认选择并发送完整选择，让用户看到的模型与请求一致。新会话禁止提供 `model_selection_version`，包括显式 `null`。

后端校验后原子保存选择、会话和首轮消息，随后 SSE `start` 返回：

```text
event: start
data: {"code":0,"message":"成功","data":{"conversation_id":"33333333-3333-4333-8333-333333333333","turn_id":"44444444-4444-4444-8444-444444444444","is_new":true,"model_selection":{"model_configuration_id":"22222222-2222-4222-8222-222222222222","reasoning":{"mode":"effort","effort":"low"}},"model_selection_version":1}}
```

使用 `start` 的会话 ID、选择和版本替换本地临时状态。其他 SSE 事件保持原有协议，内部推理仍不对外发送。

如果在 `start` 前返回选择错误，服务端没有创建本次消息和会话。界面保留消息草稿和选择，提示重选，不自动重发。开始流后仍沿用现有部分回复、取消和终止错误语义。

## 5. 已有会话：立即保存与续聊

### 5.1 恢复状态

现有 `GET /api/conversations` 每个条目，以及 `GET /api/conversations/{id}` 的 `conversation`，均增加 `ConversationSelectionFields`：

```json
{
  "model_selection": {
    "model_configuration_id": "22222222-2222-4222-8222-222222222222",
    "reasoning": {"mode": "effort", "effort": "high"}
  },
  "model_selection_version": 2,
  "model_selection_issue": null
}
```

切换会话时分别恢复其选择，不能复用全局一个选择状态。存量会话可能 `model_selection=null`，此时仅预览有效全局默认，下次有效发送才保存；前端也可先用 PATCH 明确保存。

### 5.2 立即保存

```http
PATCH /api/conversations/{conversation_id}/model-selection
```

```json
{
  "model_selection_version": 2,
  "model_selection": {
    "model_configuration_id": "22222222-2222-4222-8222-222222222222",
    "reasoning": {"mode": "effort", "effort": "low"}
  }
}
```

两个字段必填，不接受空选择或 `mode=default`。成功 `data` 是完整 `ConversationInfo`，本例新版本为 `3`，失效原因清空。

建议将控件编辑草稿与已保存选择分开：保存成功才更新确认状态，失败保留原选择并显示错误。保存期间禁止发送和重复切换；预算输入在有效整数确认后提交，避免每个未完成输入都发请求。

该接口不修改最近消息时间，不应让侧栏会话重新排序；不调用供应商。生成期间返回会话忙，不取消正在生成的请求。

### 5.3 续聊

```json
{
  "message": "再举一个例子",
  "conversation_id": "33333333-3333-4333-8333-333333333333",
  "model_selection_version": 3
}
```

续聊不发送 `model_selection`；传非空值会被拒绝，必须先 PATCH。推荐发送已保存的版本，发现另一标签页切换后先刷新会话，避免按用户未看到的选择发送。旧客户端可省略版本，使用服务端当前选择。

版本不是模型方案配置版本：管理接口使用资源 `version`，会话接口使用 `model_selection_version`。存量空选择首次在发送时初始化，选择版本递增；之后普通续聊不改变选择版本。`start` 总是返回后端确认的版本。

## 6. 配置变化和失效处理

失效原因由读取接口动态计算，不会删除历史或清空原选择：

| `model_selection_issue` | 建议展示 |
| --- | --- |
| `model_deleted` | 原模型方案已删除，请重新选择 |
| `provider_disabled` | 原供应商连接已停用，请重新选择 |
| `model_disabled` | 原模型方案已停用，请重新选择 |
| `model_unavailable` | 原模型配置暂不可用，请重新选择 |
| `reasoning_not_allowed` | 原推理设置超出当前限制，请重新选择 |
| `null` | 有选择时表示有效；无选择时表示尚未初始化 |

保存的选择不会自动降档或切换默认。固定推理值变化后，旧会话保存值不匹配也会失效；重新选中该方案后显示其新固定值，再明确保存。

首次进入、从管理页返回、窗口恢复焦点/可见，以及收到 `42201/42202` 后刷新 `/options` 和活动会话。刷新只更新有效性，不自动重选。异步响应需按账号、会话和读取序号隔离；低于本地已确认选择版本的响应不能覆盖新选择，同版本的最新失效原因仍需更新。

正在生成的一轮使用已经固定的模型快照，之后的停用或策略调整不终止该轮。下一次发送重新校验。

## 7. 管理页面后续接入

现有连接创建/PATCH/读取增加 `enabled`；创建省略时为 `true`。方案创建/PATCH/读取增加 `enabled` 和 `reasoning_policy`，创建省略策略时为固定。

方案响应保留 `available`（配置与目录兼容），新增 `selectable`（当前允许聊天选择）。停用方案可以 `available=true`、`selectable=false`，两者不能混用。

例如只开放两个档位：

```json
{
  "version": 5,
  "reasoning": {"mode": "effort", "effort": "high"},
  "reasoning_policy": {
    "mode": "selectable",
    "allowed_modes": ["effort"],
    "effort_options": ["low", "high"],
    "budget": null
  }
}
```

策略整体替换，不能只 PATCH 内部字段。`allowed_modes` 非空且不重复；开放 effort 才能填写非空、不重复的档位；开放 budget 才能填写正整数闭区间。默认值必须在范围内，收紧范围时必要的话同时改 `reasoning`。管理接口中省略字段保留原值，显式 `null` 拒绝；策略内部不适用的 `budget:null` 合法。

预算示例策略为 `{"mode":"selectable","allowed_modes":["off","budget"],"effort_options":[],"budget":{"min":1024,"max":8192}}`，具体模型必须支持此方式和区间。

停用连接不会改写子方案启停；重新启用后仍遵循各子方案状态。停用当前默认保留默认引用，但 `/options.default_selection` 变为 `null`；设置新的默认只能使用 `selectable=true` 的方案。显式连接测试仍可测试停用方案，使用方案默认值。

## 8. 错误码和恢复动作

| HTTP / code | 含义 | 前端处理 |
| --- | --- | --- |
| `401 / 40101` | 登录失效 | 沿用现有退出/登录恢复 |
| `404 / 40401` | 会话不存在、删除或属于他人 | 标记该会话不可用 |
| `409 / 40901` | 会话正在生成 | 提示等待并刷新，不自动重试消息 |
| `409 / 40902` | 管理配置版本冲突 | 保留编辑草稿，读取最新资源 |
| `409 / 40903` | 配置引用或关联兼容性冲突 | 调整引用或相关配置 |
| `409 / 40904` | 会话选择版本冲突 | 保留消息草稿，刷新会话再确认选择 |
| `422 / 42200` | 请求结构/管理配置非法 | 检查字段及策略组合 |
| `422 / 42201` | 所选模型已删除、停用或不可用 | 刷新选项和会话，要求重选 |
| `422 / 42202` | 推理值不符合当前限制 | 刷新选项和会话，要求重选 |
| `503 / 50301` | 没有会话选择及有效默认 | 允许手动选择有效方案，否则前往管理 |

不能把所有 HTTP 409 都标记为会话正在生成，也不能把所有 HTTP 404 都标记为会话删除。管理模型的 `40402/40403` 仍表示配置资源不存在。上游鉴权失败仍使用原业务错误码，不应触发用户退出。

## 9. 前端验收范围与当前限制

验收关注：无全局默认手动选择发送、固定值不可改、自选白名单/预算、切换立即保存并刷新恢复、不同会话独立选择、多标签页版本冲突、生成中禁止切换、范围收紧/停用/删除后重选、账号退出和迟到响应隔离。

涉及全局配置修改的 E2E 位于现有串行配置项目，复用真实后端和随机临时库，桌面和窄屏都验证。单元/组件测试验证控件及状态对外行为，集成测试验证 API 形状、错误恢复和请求顺序；具体入口见[前端测试说明](../frontend/README.md#测试分层与公共支撑)。

当前前端提供聊天选择器、管理启停及推理策略控件；选择失效或版本冲突时保留草稿并要求用户确认，不自动降档或重发。旧客户端请求仍兼容后端，但不会完整利用新增能力；接口也可通过 Swagger 或 HTTP 客户端验收。浏览器测试仅替换供应商边界，不验证真实付费模型的实网可用性。
