# AI 集成开放平台 —— 开放能力清单扩充设计

> 关联 spec：`docs/superpowers/specs/2026-10-15-ai-capability-market-design.md`
> 现状：`backend/app/plugin/module_ai/develop/`（能力品类 `capabilities.py`、注册表 `registry.py`、handler `handlers/*.py`）
> 本设计目标是显著扩充「开放能力清单」，把平台资产**全面、开放**地暴露为 REST + MCP 两种出口。

## 一、目标与原则

1. **全面**：把平台可复用的资产域（知识库 / 智能问数 / 工作流 / 模型 / 提示词 / 数据集 / 本体 / 应用 / 定时任务 / 训练资产等）逐一开放为能力。
2. **开放**：每个能力同时支持 REST（`POST /api/v1/open/capabilities/{code}`）与 MCP（Streamable HTTP 工具）两种出口，由应用按需授权（`channels` 字段控制 `rest`/`mcp`）。
3. **统一模式**：能力定义（code/category/perm/name/description/input_schema/returns）在 `Capability` 中登记，handler **复用既有 service**，不重写业务逻辑。
4. **权限可控**：每品类一组 `integration:{category}:{action}` 权限点；敏感写操作（删/启停/消耗资源）标 `requires_approval`，应用开启审批时先入人工审批队列。
5. **零侵入**：开放面创建的资源一律打 `source_app_id` 归属，只能由本应用读写（跨应用 404，避免枚举）。

## 二、能力品类矩阵

> 品类码在 `capabilities.py` 的 `CATEGORIES` 登记，权限点在其 `CATEGORY_PERMS` 登记。
> 「★」= 高价值优先（已有完整 service/schema）；「已存在」= 本次仅横向扩容。

| 品类码 | 中文名 | 权限域 | 现有 | 新增（以动作计） |
|--------|--------|--------|------|------------------|
| `train` | 模型训练 | `integration:train:*` | list/get/create/start/stop | 模型仓库 / 评估 / 预测 / 部署 |
| `agent` | 智能体 | `integration:agent:*` | list/get/create/update/delete | — |
| `chat` | 对话 | `integration:chat:*` | send/sessions/messages | — |
| `bot` | 机器人 | `integration:bot:*` | use | — |
| `knowledge` | 知识库 ★ | `integration:knowledge:*` | — | list/get/create/update/delete/search/ingest/文档/分类/图谱 |
| `query` | 智能问数 ★ | `integration:query:*` | — | 提问/指标/术语/资产/流水线 |
| `workflow` | 工作流 ★ | `integration:workflow:*` | — | 列表/详情/创建/更新/删除/运行/版本/调度 |
| `model` | 模型配置 | `integration:model:*` | — | 列表/详情/创建/更新/删除 |
| `prompt` | 提示词 | `integration:prompt:*` | — | 列表/详情/创建/更新/删除 |
| `dataset` | 数据集 | `integration:dataset:*` | — | 列表/详情/创建/删除/图片 |
| `app` | AI 应用 | `integration:app:*` | — | 列表/详情/创建/更新/删除 |
| `ontology` | 本体 | `integration:ontology:*` | — | 对象/属性/关系/动作/域/导出导入 |
| `cron` | 定时任务 | `integration:cron:*` | — | 列表/创建/更新/删除/触发/运行记录 |
| `sessions` | 会话 | `integration:sessions:*` | — | 列表/详情/消息/删除 |
| `space` | 个人空间 | `integration:space:*` | — | 目录/文件/上传/下载/删除 |
| `market` | 能力市场 | `integration:market:*` | — | 商品/安装/收藏/提交/分享 |
| `skill` | 技能 | `integration:skill:*` | — | 列表/详情/创建/更新/删除 |
| `tool` | 工具 | `integration:tool:*` | — | 列表/详情/创建/更新/删除 |
| `mcp` | MCP 服务器 | `integration:mcp:*` | — | 列表/详情/创建/更新/删除/启停 |
| `plugin` | 插件 | `integration:plugin:*` | — | 列表/详情/创建/更新/删除/启停 |
| `provider` | 模型供应商 | `integration:provider:*` | — | 列表/详情/创建/更新/删除 |
| `overview` | 运维审计 | `integration:overview:*` | — | 统计/健康/审计/运行时 |
| `logs` | 调用日志 | `integration:logs:*` | — | 分页/统计/导出 |

## 三、新增品类能力定义（逐条）

> 每条 = `Capability(code, category, perm, name, description, input_schema, returns, handler, mcp_tool, requires_approval)`。
> 权限点仅列品类 `action` 级，具体能力映射其 action。

### 3.1 `knowledge` 知识库（`integration:knowledge:{query,create,update,delete}`）

| code | action | name | 说明 | requires_approval |
|------|--------|------|------|-------------------|
| `knowledge.list` | query | 知识库列表 | 列出全部知识库 | — |
| `knowledge.get` | query | 知识库详情 | 按 id 查知识库 | — |
| `knowledge.create` | create | 创建知识库 | 建知识库 | — |
| `knowledge.update` | update | 更新知识库 | 改名称/描述/模型等 | — |
| `knowledge.delete` | delete | 删除知识库 | 软删（须 confirm） | ✅ |
| `knowledge.search` | query | 向量检索 | 对知识库做语义检索 | — |
| `knowledge.ingest` | update | 数据入库 | 写入文本/条目 | — |
| `knowledge.documents` | query | 文档列表 | 列出知识库文档 | — |
| `knowledge.document.delete` | delete | 删除文档 | 删文档（须 confirm） | ✅ |
| `knowledge.document.reparse` | update | 重新解析 | 重建解析 | — |
| `knowledge.categories` | query | 分类树 | 类别树 | — |
| `knowledge.category.create` | create | 新建分类 | — | — |
| `knowledge.category.update` | update | 更新分类 | — | — |
| `knowledge.category.delete` | delete | 删除分类 | — | — |
| `knowledge.graph` | query | 知识图谱 | 图谱查询 | — |
| `knowledge.graph.upsert` | update | 图谱写入 | 实体/关系写入 | — |

### 3.2 `query` 智能问数（`integration:query:*`）

| code | action | name | requires_approval |
|------|--------|------|-------------------|
| `query.ask` | ask | 自然语言问数 | — |
| `query.metrics` | query | 指标列表 | — |
| `query.metric.upsert` | update | 指标写入 | — |
| `query.terms` | query | 术语列表 | — |
| `query.asset.upsert` | update | 资产写入 | — |
| `query.pipelines` | query | 流水线列表 | — |
| `query.pipeline.run` | run | 运行流水线 | — |

### 3.3 `workflow` 工作流（`integration:workflow:*`）

| code | action | name | requires_approval |
|------|--------|------|-------------------|
| `workflow.list` | query | 工作流列表 | — |
| `workflow.get` | query | 工作流详情 | — |
| `workflow.create` | create | 创建工作流 | — |
| `workflow.update` | update | 更新工作流 | — |
| `workflow.delete` | delete | 删除工作流（须 confirm） | ✅ |
| `workflow.run` | run | 运行工作流 | ✅ |
| `workflow.versions` | query | 版本列表 | — |
| `workflow.rollback` | update | 回滚版本 | ✅ |
| `workflow.schedule` | update | 设置调度 | ✅ |
| `workflow.runs` | query | 运行日志 | — |

### 3.4 `model` / `prompt` / `dataset` / `app` / `provider`（各 `{query,create,update,delete}`）

每个提供标准 CRUD：`<domain>.list` / `.get` / `.create` / `.update` / `.delete`；写操作复用既有 service 的 create/update/delete，敏感删除置 `requires_approval`。

### 3.5 `ontology` 本体（`integration:ontology:{query,execute,manage}`）

`ontology.objects` / `ontology.object.upsert` / `ontology.properties` / `ontology.relations` / `ontology.domains` / `ontology.export` / `ontology.import` / `ontology.actions.execute`。

### 3.6 `cron` 定时任务（`integration:cron:{query,create,update,delete,run}`）

`cron.list` / `cron.get` / `cron.create` / `cron.update` / `cron.delete`（✅）/ `cron.run`（✅）/ `cron.runs`（query）。

### 3.7 `sessions` / `space` / `market` / `skill` / `tool` / `mcp` / `plugin`

各提供标准 CRUD + 域内关键操作（如 `space.upload`/`space.download`、`market.install`、`mcp.toggle`、`tool.test` 等）。

### 3.8 `overview` / `logs`

只读运维类：`overview.stats` / `overview.health` / `overview.audit` / `logs.page` / `logs.stats` / `logs.export`。

### 3.9 `train` 横向扩容（`integration:train:*` 扩展 action）

新增 `integration:train:model/repo:eval:predict:deploy` 动作权限，注册
`train.models` / `train.model_repo.create` / `train.evals` / `train.eval.create` / `train.predicts` / `train.deploys` / `train.deploy.create` 等。

## 四、开放性保障

1. **出口统一**：REST 用 `POST /open/capabilities/{code}`（`openapi.py` 统一鉴权/限流/审批/审计管道）；MCP 用 `mcp_server.py` 的 Streamable HTTP。两出口共用 `invoke_capability`，行为一致。
2. **按需授权**：应用创建/编辑时勾选能力码 + 出口（`channels`），授权收敛到应用级，避免「全开」。
3. **分权**：只读（query）与写操作（create/update/delete/run）权限点分离；一键审批 + 配额 + 限流覆盖全部新能力（`check_open_limits` 按品类日配额，`requires_approval` 敏感操作入队）。
4. **审计不泄密**：入参剔除凭证键、超长截断，绝不落 `appkey`/`token`。
5. **数据隔离**：`source_app_id` 归属 + 跨应用 404，防止第三方枚举/越权。

## 五、落地改动面

- `backend/app/plugin/module_ai/develop/capabilities.py`：新增品类与权限点。
- `backend/app/plugin/module_ai/develop/handlers/*.py`：每个新品类一个 handler 文件，`register_<category>_capabilities()` 注册。
- `backend/app/plugin/module_ai/develop/handlers/__init__.py`：挂载各 `register_*`。
- `frontend/src/views/module_ai/develop/index.vue`：`CATEGORIES` 补品类中文名；应用新建/编辑表单的能力勾选列表自动来自 `getCapabilities`（无需手改）。
- 前端 i18n：新增品类中文名键（`develop_cat*`）。

## 六、实施阶段划分（见计划）

- **阶段 A（高价值，先做）**：`knowledge`、`query`、`workflow`、`app`、`cron`、`model`、`prompt`。
- **阶段 B（资产广度）**：`dataset`、`ontology`、`sessions`、`space`、`provider`。
- **阶段 C（能力资产 + 运维）**：`skill`、`tool`、`mcp`、`plugin`、`market`、`overview`、`logs`、`train` 横向扩容。
