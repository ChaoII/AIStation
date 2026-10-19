# 个人工作空间（Personal Workspace）设计文档

- 日期：2026-10-19
- 状态：已批准（用户整体批准，进入实施计划阶段）
- 模块：`backend/app/plugin/module_ai/space/` + `frontend/src/views/module_ai/space/`

## 1. 背景与目标

AIStation 平台在 AI 管理模块下已有「AI 工作台」（资产聚合 + 定时任务 + 聊天），但没有任何「个人文件空间」能力：用户没有统一的地方存放个人文件，AI 智能体产出的内容（报告、分析结果等）也没有落盘位置，智能体在处理任务时无法引用用户自己的文件。

本特性新增「个人工作空间」：

1. 每个用户拥有**严格私有的文件空间**，可**上传 / 下载 / 在线预览**文件；
2. 文件按**多级文件夹**组织（网盘式）；
3. AI 智能体生成的文件**自动保存**到用户个人工作空间（智能体拥有保存/列出/读取工具）；
4. AI 智能体处理任务时**可选择**个人空间内容（用户对话时勾选 + 智能体自主访问，两者都要）。

### 成功标准

- 用户能在 AI 管理下进入「个人工作空间」，完成上传→列表→预览→下载→移动→删除全链路；
- 用户 A 无法访问用户 B 的任何文件；
- 智能体在对话中调用工具即可把内容保存为工作空间文件，文件来源标记为「AI 生成」；
- 用户在对话中可从工作空间勾选文件（图片/文本/PDF/Office）作为智能体输入；
- 配额（单文件上限 + 每用户总量）生效且前端可见。

## 2. 现状调研结论（2026-10-19）

- 无任何「个人工作空间」相关代码（全仓搜索无结果）。
- 已有 `module_ai/workspace`（AI 工作台，`/ai/workspace`），是资产聚合/定时任务语义，**不是**文件空间；本特性与其完全独立、零侵入。
- 文件存储已有两条通路：
  - 本地 `static/upload`（`module_common/file`，单机、无配额核算）；
  - **RustFS/S3**（`app/utils/s3_client.py`，已具备 upload/download/get_object/delete/presigned_url，知识库 `module_ai/knowledge` 已实现完整的文档上传/下载/在线预览模式）。
- 用户模型 `sys_user`（`module_system/user/model.py`），当前用户经 `AuthPermission` 依赖注入（`auth.user.id`）。
- 菜单/权限由 `init_app._ensure_ai_menus()` **启动时幂等补齐**（含 AI 页面列表与按钮权限码，格式 `module_ai:<模块>:<动作>`），无需手工 INSERT。
- 智能体统一走 agno：`agno_tools.business.build_business_tools()` 包装 `assistant.tools.TOOL_REGISTRY` 为 agno Function；`user_id` 通过 `business.USER_ID_CONTEXT`（ContextVar）注入，模型不可见。
- `assistant/controller.py` 的 `/stream` 已支持 `files`（`name/type/dataUrl`，图片走视觉、文档抽文本）。
- 注意：app/agent 运行台（`run_agno_tool_stream`）用动态工具**覆盖**默认业务工具集，新增工作空间工具必须在那里**显式并入**。
- 迁移纪律：插件模块表由启动 `create_all` 补齐（绿库）；手写 Alembic 迁移必须 `has_table()` 守卫（dev 库有 400+ 影子表，禁 autogenerate）。

## 3. 方案选型（已确认：方案 1）

| 方案 | 结论 |
|---|---|
| **1. 独立新模块 `module_ai/space` + RustFS/S3** | ✅ **采纳**。语义干净、严格用户隔离、复用成熟存储链路、对现有工作台零侵入 |
| 2. 扩展现有 `module_ai/workspace` | ❌ 拒绝。语义混杂、现有表无文件元信息、侵入大 |
| 3. 复用知识库文档链路 | ❌ 拒绝。知识库是共享数据源 + RAG 语义，会触发不必要的向量化 |

存储介质：**RustFS/S3**（已确认）；本地目录仅作备选，不支持。

## 4. 设计

### 4.1 模块与菜单

- 后端：`backend/app/plugin/module_ai/space/`（controller / service / model / schema；插件自动发现，容器前缀 `/ai`，路由前缀 `/space`）。
- 权限码：`module_ai:space:query`（查看/预览）、`module_ai:space:upload`、`module_ai:space:download`、`module_ai:space:delete`、`module_ai:space:manage`（文件夹新建/重命名/移动）。
- 前端：`frontend/src/views/module_ai/space/index.vue`；API 封装 `frontend/src/api/module_ai/space.ts`。
- 菜单：「个人工作空间」，`route_name=AiPersonalSpace`，路径 `/ai/space`，图标 `el-icon-FolderOpened`，位置排在「AI 工作台」之后；在 `init_app._ensure_ai_menus()` 的 pages 列表与 `AI_BUTTON_PERMS` 中补齐（幂等）。
- 与「AI 工作台 `/ai/workspace`」无耦合；菜单路由名不能与现有 `AiWorkspace`/`AiWorkbench` 冲突。

### 4.2 数据模型（两张新表，均继承 `ModelMixin`）

**`ai_space_folders`**

| 列 | 类型 | 说明 |
|---|---|---|
| id | BigInteger PK | |
| name | String(255) | 文件夹名 |
| user_id | BigInteger, index | 归属用户 |
| parent_id | BigInteger, FK(self), nullable | `NULL` = 根目录 |
| status / created_time / updated_time / is_deleted / deleted_time | ModelMixin | 软删 |

**`ai_space_files`**

| 列 | 类型 | 说明 |
|---|---|---|
| id | BigInteger PK | |
| uuid | String(64), unique | 对象文件名用 |
| folder_id | BigInteger, FK(folders), nullable | `NULL` = 根目录 |
| user_id | BigInteger, index | 归属用户 |
| name | String(255) | 文件名（含扩展名） |
| ext | String(32) | 扩展名（小写，不含点） |
| file_type | String(32) | image/pdf/txt/md/csv/json/docx/video/audio/other |
| mime_type | String(128) | |
| size | BigInteger | 字节 |
| object_key | String(512), unique | S3 key |
| source | String(16) | `upload`=用户上传 / `agent`=智能体生成 |
| status / created_time / updated_time / is_deleted / deleted_time | ModelMixin | 软删 |

隔离规则：所有查询强制 `user_id == 当前用户`；不做任何共享视图（管理员也不看他人文件，保持「个人」语义；后台审计留待后续需求）。

建表方式：模型进 `create_all`（绿库自动建）；另手写 Alembic 迁移 `2026_10_19_ai_space_tables.py`（`sa.inspect(bind).has_table()` 守卫，参考 `2026_10_16_ai_workspace.py`）。

### 4.3 存储与配额

- 存储：复用 `app/utils/s3_client.py`（RustFS/S3 兼容）。object key = `ai-space/{user_id}/{YYYYMMDD}/{uuid}{ext}`，上传时设置 ContentType；bucket 沿用 `s3_client` 默认 `aistation-annotation-{dev|prod}`（以 key 前缀隔离，不新增 bucket）。
- 配额（`config/setting.py` 新增，环境可覆盖）：
  - `AI_SPACE_MAX_FILE_MB`：默认 `200`（单文件上限）；
  - `AI_SPACE_QUOTA_MB`：默认 `10240`（10GB，每用户总配额）。
- 校验：上传与 Agent 保存均校验 `size <= max_file_bytes` 与 `SUM(size) + size <= quota`；超限返回明确错误（含已用/配额）。
- 上传实现（MVP）：与知识库一致，multipart 直传（`UploadFile` 全量读入 → `asyncio.to_thread(s3_client.upload_fileobj, ...)`）；超大文件后续可换 presigned PUT 分片（优化项，非本期）。

### 4.4 后端 API（`/api/v1/ai/space`）

文件夹：

- `GET /folders/tree` — 当前用户文件夹树（含每个文件夹文件数，前端展示可后补）
- `POST /folders/create` — `{name, parent_id?}`
- `PUT /folders/update/{id}` — 重命名
- `DELETE /folders/delete` — body 传 `folder_id`；**级联删除**文件夹内所有文件（DB 软删 + S3 批量删）；前端二次确认写明数量

文件：

- `GET /files/list` — `folder_id?/keyword?/file_type?/page_no/page_size`，返回 `{items,total,has_next,...}`，按时间倒序
- `POST /files/upload` — `UploadFile` + `folder_id?`，返回文件元信息
- `GET /files/{id}/download` — `StreamingResponse`（attachment + UTF-8 文件名，参考知识库 `download_document`）
- `GET /files/{id}/preview` — 按 `file_type`：
  - 文本类（txt/md/csv/json）→ 返回 `{content}`（文本/JSON，前端渲染；>500KB 截断并带 `truncated` 标记）
  - 图片 → 返回流 `image/*`（前端 `<img>`）
  - PDF / docx → 前端下载 blob：PDF 用 `vue-pdf-embed`（objectURL），docx 用 `mammoth.convertToHtml` —— **与知识库预览策略完全一致**（知识库即前端 mammoth，非后端转 HTML）
  - 其他类型 → 400「该类型暂不支持预览」（提示可下载后查看）
- `PUT /files/rename` — `{file_id, name}`（仅改 DB 记录，不动 S3 对象）
- `POST /files/move` — `{file_id, folder_id}`（folder_id 可为 null 根目录；校验目标文件夹属于同一用户）
- `DELETE /files/delete` — body 传 ids 列表；软删 DB + 删 S3 对象
- `GET /space/quota` — `{used_bytes, quota_bytes, max_file_bytes}`

### 4.5 智能体集成

**A. 智能体工具**（注册进 `assistant/tools.py::TOOL_REGISTRY`；`build_business_tools` 自动包装；`user_id` 走现有 `USER_ID_CONTEXT`，模型不可见）：

| 工具名 | 参数 | 说明 |
|---|---|---|
| `workspace_save_file` | `name, content, file_type?`（默认按 name 推断） | 保存文本/Markdown/CSV/JSON 到当前用户空间，`source=agent`；返回 `{file_id, name, size}`；超配额/超限返回错误 |
| `workspace_list_files` | `keyword?/folder_id?/limit?` | 列出当前用户文件（名称/类型/大小/时间），供智能体发现内容 |
| `workspace_read_file` | `file_id` | 读取文本类内容（txt/md/csv/json 原文；pdf/docx 抽取文本；图片提示「请查看图片文件」；文本超 100KB 截断防 token 爆炸） |

**覆盖范围**：

- assistant 聊天/助手（默认业务工具）→ 自动获得上述工具；
- app/agent 运行台（`run_agno_tool_stream`，动态工具覆盖默认）→ 实现时将工作空间工具**并入**动态工具列表（`build_dynamic_tools(...) + workspace 工具`），确保所有 Agent 场景可用。

**B. 用户挑选空间文件给 Agent**：

- `AssistantUIStreamSchema.files` 扩展支持 `{"type":"workspace","file_id":123,"name":"..."}` 引用；
- `agno_service._process_uploaded_files` 识别 `type=workspace` → 从 `space` 服务取对象：图片转 `Agno Image`，文档用现有 `_extract_doc_text` 抽文本拼上下文；
- 前端提供通用 `SpaceFilePicker` 组件（el-dialog：文件夹树 + 文件列表 + 多选），接入 AI 对话入口（MVP 先接入 assistant 对话页；后续可按需接入 app/agent 运行台）。

### 4.6 前端页面（网盘式，`space/index.vue`）

- 布局：左侧 `el-tree` 文件夹树（新建/重命名/删除）；右侧面包屑 + 搜索框 + 类型筛选 + 上传按钮 + `el-table` 文件列表。
- 列表列：名称（图标按类型）、大小（前端格式化）、类型、来源（`el-tag`：「AI 生成」/「用户上传」）、更新时间、操作（预览/下载/重命名/移动/删除）。
- 顶部：存储配额 `el-progress`（已用/总量）。
- 上传：`el-upload`（拖拽 + 点击），上传中显示进度；完成后**局部刷新**当前目录（不整页刷新）。
- 预览弹窗（`el-dialog`）：文本类代码块/`v-html`、图片 `<img>`、PDF `vue-pdf-embed`（知识库已引入）、docx 后端 HTML。
- 删除/移动/级联删除：`ElMessageBox.confirm` 二次确认，文案写明影响范围与数量（如「将删除 12 个文件，且不可恢复」），按钮语义明确（「删除/取消」）。
- 按钮全部 `v-hasPerm`（字符串形式权限码）；样式严格按 Element Plus + `--el-*` 变量；参照 `module_ai/knowledge` 与 `module_system/param`；不自定义 font-size，不手造主题外壳。

### 4.7 测试与验收

后端测试 `tests/test_ai_space.py`（S3 用 mock/测试替身，参照现有 knowledge 测试方式）：

- 用户隔离：A 无法读取/下载/删除 B 的文件（直接构造越权请求断言 404/403）；
- 配额：单文件超 `AI_SPACE_MAX_FILE_MB` 拒绝；总配额超限拒绝；
- 文件夹：树构建、重命名、级联删除（文件 + 对象删除）；
- 文件：上传（类型/大小校验）、列表分页/搜索、下载头、预览分类型、重命名、移动（跨用户目标拒绝）；
- Agent 工具：`workspace_save_file` / `workspace_list_files` / `workspace_read_file`（含截断）；
- files 引用：`_process_uploaded_files` 对 `{"type":"workspace","file_id":...}` 的处理。

前端：`pnpm run type-check`、`pnpm run lint` 通过；后端 `ruff check` 通过（涉及既有文件仅新增代码）。

验收（真实环境手动）：

1. 上传文件（图片/PDF/docx/txt/csv）→ 列表可见 → 各类型预览正常 → 下载文件名正确；
2. 新建多级文件夹、移动文件、重命名、级联删除（确认文案含数量）；
3. 配额：单文件超限提示；总量超限提示；
4. 智能体对话：「帮我写一份关于 xx 的分析报告并保存」→ Agent 调用 `workspace_save_file` → 文件出现在空间（来源=AI 生成）；
5. 对话前从空间勾选图片/文本/PDF → Agent 能正确引用（图片视觉 / 文档文本）。

### 4.8 非目标（本期不做）

- 回收站（删除即永久，靠二次确认保证）；
- 文件分享/协作/共享链接；
- Agent 生成图片/音频（本期仅文本类内容保存）；
- 改造现有 AI 报告 / 表格导出为文件落盘；
- 对象存储切换本地目录、S3 presigned 分片上传。

## 5. 风险与开放问题

| 风险/问题 | 处理 |
|---|---|
| `_process_uploaded_files` 对 workspace 引用需要查 DB + S3，可能拖慢首 token | 仅拉取所选文件，限制单文件拉取大小（如 20MB），其余走抽取文本 |
| S3 大规模删除（级联删除文件夹）耗时 | 用 `s3_client.delete_objects` 分批并发（已有实现），前端先给 loading |
| app/agent 运行台工具覆盖导致工作空间工具缺失 | 已在设计中显式并入（4.5 覆盖范围） |
| 预览 docx → HTML 依赖现有解析实现 | 实现时复用 `knowledge/service.py` 的相同工具函数 |
| 存量库无新表 | create_all + 手写迁移（has_table 守卫）双保险 |
