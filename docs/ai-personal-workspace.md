# AI 个人工作空间

> 设计文档：`docs/superpowers/specs/2026-10-19-personal-workspace-design.md`
> 实施计划：`docs/superpowers/plans/2026-10-19-personal-workspace.md`

## 一、它解决什么问题

平台原先没有「用户自己的文件空间」：用户上传给 AI 的图片/文档随会话即用即弃，
智能体生成的报告、数据摘要没有落点，也无法把已有文件再喂给智能体。

「个人工作空间」为每个用户提供一套**网盘式**空间（多级文件夹 + 文件）：

- 用户可以上传 / 下载 / 在线预览自己的文件；
- AI 智能体（app / agent / 助手）通过工具把生成的文件**自动保存到用户空间**；
- 用户对话时**从空间勾选文件**引用给智能体（图片走视觉、文档抽取文本）；
- 按用户强隔离（所有查询强制 `user_id` 过滤，object key 前缀 `<user_id>`）。

存储走 RustFS / S3 兼容对象存储（`app.utils.s3_client`），数据库只存元信息。

## 二、数据模型

| 表 | 用途 | 关键列 |
|----|------|--------|
| `ai_space_folders` | 多级文件夹 | `name`、`user_id`、`parent_id`（NULL=根） |
| `ai_space_files` | 文件元信息 | `folder_id`、`user_id`、`name`、`ext`、`file_type`、`mime_type`、`size`、`object_key`(唯一)、`source`(upload/agent) |
| `ai_space_quota_requests` | 扩容申请 | `user_id`、`target_mb`、`reason`、`status`(pending/approved/rejected)、`reviewed_by`、`review_note`、`review_time` |
| `ai_space_user_quota` | 按用户配额覆盖 | `user_id`(唯一)、`quota_mb`、`updated_by` |

- 四表均继承 `ModelMixin`（软删：`is_deleted` / `deleted_time`）。
- 迁移文件：`backend/app/alembic/versions/2026_10_19_ai_space_tables.py`、
  `backend/app/alembic/versions/2026_10_21_ai_space_quota.py`（均手写 + `has_table` 幂等守卫）。

```bash
cd backend && uv run main.py upgrade --env=dev
```

## 三、权限码与菜单

权限码（`backend/app/scripts/init_app.py` 的 `AI_BUTTON_PERMS`）：

| 权限码 | 含义 |
|--------|------|
| `module_ai:space:query` | 查看个人空间（列表/树/预览/配额）、提交扩容申请、对话引用入口 |
| `module_ai:space:upload` | 上传文件 |
| `module_ai:space:download` | 下载文件 |
| `module_ai:space:delete` | 删除文件/文件夹（含级联） |
| `module_ai:space:manage` | 新建/重命名文件夹、移动/重命名文件 |
| `module_ai:space:quota_review` | 审核个人空间扩容申请（管理员页） |

菜单：`AI 管理 → 个人工作空间`（`/ai/space`，组件 `module_ai/space/index`）、
`AI 管理 → 空间扩容审核`（`/ai/space/quota`，组件 `module_ai/space/quota-review`，权限 `module_ai:space:quota_review`）。

**存量库如何生效**：菜单与按钮权限由 `_ensure_ai_menus()` 启动时幂等补齐并授权 admin，
重启一次后端即可，无需手工 INSERT。

## 四、配额（默认 2GB + 申请扩容）

`backend/app/config/setting.py`：

| 配置 | 默认 | 说明 |
|------|------|------|
| `AI_SPACE_MAX_FILE_MB` | 200 | 单文件上限（MB） |
| `AI_SPACE_QUOTA_MB` | 2048 | 每用户总配额（MB，默认 2GB） |

**生效配额**：有 `ai_space_user_quota` 覆盖则用覆盖值，否则回落到 `AI_SPACE_QUOTA_MB`。
超限上传返回 400 中文提示；配额统计口径为「未删除文件 size 之和」。

**扩容流程**：用户点「申请扩容」→ 提交申请（`target_mb` 必须大于当前生效配额、同一用户
只能有一笔待审）→ 管理员在「空间扩容审核」页通过/驳回 → 通过时为该用户 upsert
有效配额（`ai_space_user_quota`），配额立即生效。

## 五、API 一览（`/api/v1/ai/space`）

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/folders/tree` | space:query | 文件夹树 |
| POST | `/folders/create` | space:manage | 新建文件夹（`{name, parent_id}`） |
| PUT | `/folders/update/{id}` | space:manage | 重命名 |
| DELETE | `/folders/delete` | space:delete | 删除（body=id，级联软删子文件夹与文件并删对象） |
| GET | `/files/list` | space:query | 分页列表（`folder_id/keyword/file_type/page_no/page_size`） |
| POST | `/files/upload` | space:upload | multipart（`file` + `folder_id`） |
| GET | `/files/{id}/download` | space:download | 流式下载（`Content-Disposition`） |
| GET | `/files/{id}/preview` | space:query | 文本类返回 `{kind:"text",content,truncated}`；image/pdf/docx 走对象流 |
| PUT | `/files/rename` | space:manage | `{file_id, name}` |
| POST | `/files/move` | space:manage | `{file_id, folder_id}` |
| DELETE | `/files/delete` | space:delete | body=file_ids 数组 |
| GET | `/quota` | space:query | `{used_bytes, quota_bytes, max_file_bytes, default_quota_bytes, has_pending_request}` |
| POST | `/quota/request` | space:query | 提交扩容申请 `{target_mb, reason}`（大于当前生效配额、无待审） |
| GET | `/quota/requests/mine` | space:query | 我自己的扩容申请（倒序） |
| GET | `/quota/requests` | space:quota_review | 全部扩容申请（`?status=`, 带 `username`） |
| POST | `/quota/requests/{id}/review` | space:quota_review | 审核 `{approve, quota_mb?, note}`；通过则 upsert 用户配额 |

删除类接口均为**软删元信息 + 删除对象**；对象删除失败仅记日志不阻塞。

## 六、智能体工具（Agent / App 自动使用）

注册在 `assistant/tools.py::TOOL_REGISTRY`，经 `agno_tools/business.py::build_workspace_tools()`
包装为 Agno 工具，由 `run_agno_tool_stream` 显式并入（app/agent 运行台）：

| 工具 | 参数 | 说明 |
|------|------|------|
| `workspace_save_file` | `name`, `content`, `file_type?` | 保存文本到用户空间（`source=agent`），返回 `{file_id,name,size}` |
| `workspace_list_files` | `keyword?`, `limit?` | 列出用户空间文件 |
| `workspace_read_file` | `file_id` | 读取文本内容（pdf/docx 抽取；图片报错；>100KB 截断） |

`user_id` 经 ContextVar 注入，对模型不可见。

## 七、对话引用个人空间文件

助手（`AiAssistant` 浮窗）输入区新增「个人空间」按钮（权限 `module_ai:space:query`），
弹窗内选择文件夹与文件（可多选）；发送时把 `{type:"workspace", file_id, name}` 并入
消息的 `files` 载荷。后端 `agno_service._process_uploaded_files` 识别 `type=="workspace"`，
经 `_resolve_workspace_file` 读取真实字节：图片走视觉，其余文档抽取文本；读取失败自动跳过不阻断对话。

## 八、文件类型与预览

- 分类由扩展名优先、mime 兜底（`space/filetype.py`）：图片 / pdf / docx / txt / md / csv / json / 视频 / 音频 / 其他。
- 不支持的类型上传直接 400（提示允许的类别）。
- 预览：文本类后端返回内容（>500KB 截断并标记）；图片 `<img>`；PDF `vue-pdf-embed`；
  docx 前端 `mammoth`（与知识库一致）。
