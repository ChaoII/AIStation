# 全局问题审计清单（2026-10-23）

> 范围：后端安全与鉴权、后端框架层与健壮性、前端框架层与 UI 一致性、AI 管理模块完备性。
> 性质：**只读审计**，未修改代码。已修复推送项（OperationLogRoute 脱敏、角色删除/停用保护、录像防重复、webrtc 信令鉴权、登录 RSA 加密、成功提示显式化）不再列入。
> 严重度：🔴 高 / 🟠 中 / 🟢 低，⭐ 表示「框架层面」（影响通用体系，非单页）。

---

## 一、后端安全与鉴权

### 🔴 高危

| # | 位置 | 问题 | 影响 | 框架 | 建议 |
|---|------|------|------|:---:|------|
| S1 | `module_system/auth/controller.py:205` `get_auto_login_token_controller` | `POST /auth/auto-login/token?user_id=X` **无鉴权**，任意 user_id 都能生成免登录 token，再 `POST /auth/auto-login` 兑换**完整 JWT** | **认证绕过**，遍历 user_id 即可接管任意账号（含超管） | 否 | 加 `AuthPermission/get_current_user`，仅管理员为自己/受控用户铸票；`auto-login` 兑换校验来源/频控 |
| S2 | `module_system/user/controller.py:179` + `service.py:510` `forget_password_service` | **忘记密码无鉴权**、`mobile` 未校验、无验证码，仅凭 username 即可重置密码 | 未登录者枚举用户名即可接管普通用户 | 否 | 加鉴权或走短信/邮箱验证码强校验 + 限流 |
| S3 | `module_system/user/controller.py:153` + `schema.py:110` `UserRegisterSchema.role_ids=[1]` + `service.py:480` | **注册无鉴权** 且默认授予 `role_id=1`（管理员），且 `role_ids` 可自由指定任意角色 | 匿名注册即得管理员权限（提权） | 否 | 默认普通用户角色、禁止前端指定高权限角色、服务端校验白名单 / 注册开关 + 验证 + 限流 |
| S4 | `module_system/params/controller.py:267` `get_init_obj_controller` | `GET /system/param/info` **无鉴权**，原样回显全部 `system_config`（含 `notify_smtp_pass`、`notify_webhook_secret`） | 未登录者读取 SMTP 密码/Webhook 密钥明文 | 否 | 只返回非敏感白名单键或对敏感键掩码，最稳妥加鉴权 |

### 🟠 中危

| # | 位置 | 问题 | 影响 | 框架 | 建议 |
|---|------|------|------|:---:|------|
| S5 | `app/core/permission.py` + `base_crud.py` | `TenantMixin.tenant_id` 加了但**权限过滤从不按 tenant 过滤**，`create` 也不自动注入租户 | 多租户数据互通 | ⭐ | 非超管时 `tenant_id==当前租户` 强制过滤，create 自动写入 |
| S6 | `config/setting.py:120-123` + `middlewares.py:25` | CORS 默认 `ALLOW_ORIGINS/METHODS/HEADERS=["*"]` | 任意源可调公开接口，放大 S1/S2/S3/S4 利用面 | ⭐ | 生产用显式域名白名单，收紧方法/头，避免 `*`+凭据 |
| S7 | `module_common/file/service.py:75` `_validate_download_path` | 路径校验用 `startswith(upload_root)` 前缀匹配 | 可读上传目录**同级前缀**目录文件 | 否 | 改用 `Path.resolve().is_relative_to()` |

### 🟢 低危

| # | 位置 | 问题 |
|---|------|------|
| S8 | `dict/controller.py:501` `GET /dict/data/info/{type}` | 无鉴权（登录页需用，倾向设计如此，确认即可） |
| S9 | S1/S2/S3 均无验证码与限流 | 可账号枚举/爆破/批量注册，需统一加载行为验证+频控 |

---

## 二、后端框架层与健壮性

### 🔴 高危

| # | 位置 | 问题 | 影响 | 框架 | 建议 |
|---|------|------|------|:---:|------|
| F1 | `base_crud.py` `delete()/set()/restore()/clear()` (L296-444) | **写路径不应用数据权限过滤**，直接按 `pk.in_(ids)` 批量操作 | 拿到写权限即可删/停/恢复**数据范围外**记录 | ⭐ | 在写操作 where 追加权限条件 |
| F2 | `base_crud.py` 全部 `except Exception` `raise CustomException(msg=f"...{e!s}")` | 把原始异常文本塞进 msg，绕过 SQLAlchemyError 脱敏 | 生产环境泄露表名/约束/路径 | ⭐ | 仅日志记录 `e!s`，msg 用固定文案 |
| F3 | `app/core/ap_scheduler.py:655-678` `_task_wrapper` `exec(code_block)` | **定时任务节点可配置任意 Python 代码**，服务端 `exec` 无沙箱 | 能建任务的用户即 RCE | 否 | 确认 cronjob 建任务权限是否仅限超管；否则套 AST 白名单沙箱 |
| F4 | （同 S5）多租户隔离未在权限/CRUD 层强制 | 跨租户读写 | ⭐ | 同 S5 |

### 🟠 中危

| # | 位置 | 问题 | 框架 | 建议 |
|---|------|------|:---:|------|
| F5 | `base_crud.py` `tree_list()` L105-149 | 数据权限只过滤根查询，`selectinload` 子节点不过滤 | ⭐ | 子树逐层过滤或按权限白名单裁剪 children |
| F6 | `base_crud.py:483,485` `func.date_format` | `date/month` 用 MySQL 专用函数，PG/SQLite 报未定义 | ⭐ | 改跨方言写法，加 PG/SQLite 两端测试 |
| F7 | `middlewares.py` `DBSessionMiddleware` L283-323 | 长连接 SSE 期间请求会话一直持有 DB 连接 | ⭐ | 流式端点不要持有连接，流开始即释放 |
| F8 | `middlewares.py` `_blocked_response` L124-158 | IP 黑白名单/演示模式拦截 **fail-open**（配置读取失败即放行） | ⭐ | 读取失败 fail-closed 并告警/缓存最近配置 |
| F9 | `exceptions.py` `ValueExceptionHandler` L205-218 | `ValueError` 的 `str(exc)` 原样回显 | ⭐ | 套 `_safe_error_data`，非 DEBUG 返回通用文案 |
| F10 | `ap_scheduler.py` L57-73 | 模块级单例调度器 + 共享 jobstore，**多 worker/多进程会重复调度** | ⭐ | 引入 Redis 分布式锁，或固定单 worker 承载调度 |

### 🟢 低危 / 观察项

| # | 位置 | 问题 |
|---|------|------|
| F11 | `base_crud.py` `page()` 深分页，`page_size` 未服务端强约束 | 大表深页 + 大 page_size 全表扫；建议统一走 `PaginationQueryParam` 并限上限 |
| F12 | `redis_crud.py` 用阻塞式 `redis.keys()` 全量扫描 | 键多时阻塞；建议 `SCAN` 迭代 |
| F13 | `init_app.py` NOTIFY_PARAMS 敏感配置明文存 `sys_param`；`_send_sms` 把 secret 随请求体 POST | 建议配置落库加密/接口掩码，SMS 请求体不带明文 secret |
| F14 | `_send_email/_send_sms` 无重试（webhook 有） | 观察项，best-effort 语义 |

---

## 三、前端框架层与 UI 一致性

### 🔴 高危（框架层，影响所有 CRUD 页）

| # | 位置 | 问题 | 建议 |
|---|------|------|------|
| U1 | `components/CURD/PageContent.vue:49-58` | 默认 `<el-table>` 无 `border/stripe`、无 `#empty` 空态 | 默认补 `border stripe` + 内置 `el-empty :image-size="80" description="暂无数据"` |
| U2 | `PageContent.vue:500` | 默认分页 `layout` 含 `jumper`，与规范不符 | 去掉 `jumper` |
| U3 | `PageContent.vue:552-555` | 默认 `deleteConfirm` 文案「确认删除?/确定」未写数量+不可逆 | 改语义明确文案 |

### 🟠 中危

| # | 位置 | 问题 | 建议 |
|---|------|------|------|
| U4 | 全 `src`（约 30 文件，68 个 lint 问题） | **全量 lint 远超已知 3 文件**，含 `record(7)`、`TimeSeriesPanel(6)`、`task/detail(6)`、`provider(4)`、`AnnotationToolbar(3)`、`Notification(3)`、`DetectionOverlay(3)`、`model(3)`、`PageContent(1)` 等 | 逐一清理；尤其框架文件自身 |
| U5 | `module_ai/app:510` `model:433` `prompt:453`、`module_video/face_gallery:341` `deploy:513` `edge:273` | 删除确认文案仅「确认删除所选X?」，未写数量+不可逆 | 补全文案 |
| U6 | `components/Frame/index.vue:31`、`module_ai/provider` `.ai-provider-page`、`module_monitor/cache` `.cache-page-tabs` | scoped 覆盖布局类（含死代码） | 改非 scoped + 唯一类名 |

### 🟢 低危

| # | 位置 | 问题 |
|---|------|------|
| U7 | `module_ai/develop/EmbedDialog:77`、`workflow/WorkflowEditor:585/733`（缺 stripe）、`module_monitor/cache:221`（缺 border） | 裸/半裸表格 |
| U8 | `module_video/record:492`、`module_ai/space:328`、`overview:1139`、`market/MarketBrowse:146`、`MarketReview:121`、`ontology/OntInstanceExplorer:127` | 分页 layout 不统一 |
| U9 | `module_synthesis/synthesis:173`、`EmbedDialog:83` | 空态用 `empty-text` 而非 `el-empty` |
| U10 | `workspace/AgentFormDialog:125`、`generator/gencode`（多处） | 内联 `style="font-size"` |
| U11 | `module_ai/develop:2223`、`module_annotation/stats`、`knowledge` | 硬编码 `#409eff` 等 |
| U12 | `module_video/live`（220/260px）、`playback`（240px） | 左栏宽度非 240px（视频墙自定义页，确认是否豁免） |
| U13 | `module_train/task:379`、`module_ai/workshop:352` | `v-model="obj[key]"` 独立对象+动态 key，el-switch 布尔 undefined 风险 |
| U14 | `module_task/cronjob/job:721` `handleClearConsole` | 「清空」控制台无二次确认 |

---

## 四、AI 管理模块完备性

> 整体完成度高，核心闭环（工作流分类、Agent 绑定、SSE 协议边界、委托转译去重、运行时模型解析、菜单权限幂等、知识库向量双写+回退、脚本沙箱）均正确。缺口集中在「观测/成本」与「超时兜底」。

### 🔴 高危

| # | 位置 | 问题 | 影响 | 建议 |
|---|------|------|------|------|
| A1 | `overview/service.py:369-418`、`apps/service.py:456-467`、`agent/service.py:606-614`、`workflow/service.py:539-548`、`assistant/agno_service.py:364-371` | **调用日志 `prompt_tokens/completion_tokens/cost` 恒为 0**（`run_agno_tool_stream` 从不写 `state["usage"]`） | 成本核算/按模型 token 统计失真 | 运行结束后从 agno 结果提取 usage 回填，各 add_log 统一上报 |
| A2 | `overview/model.py:22` | `cost` 列类型 `Integer` 但语义是 float（元），补列逻辑用 `NUMERIC`，新旧库不一致 | 成本精度丢失/写失败 | 改 `Numeric` 并手写迁移对齐 |

### 🟠 中危

| # | 位置 | 问题 | 建议 |
|---|------|------|------|
| A3 | `mcp/tools.py:71-80` `connect_mcp_tools` | `MCPTools.connect()` 无超时，不可达服务器可能挂起 | `asyncio.wait_for` 包超时（如 10s），失败跳过 |
| A4 | `agno_tools/agent_factory.py:37-54`、`assistant/agno_service.py:199-211`、`apps/service.py:165` | agent/app/assistant 运行无强制超时；**`app.timeout` 落库但不生效**（死字段） | `build_model` 透传 timeout，运行外层 `wait_for` 兜底 |
| A5 | `agent/model.py:11-24` + `service.py:203-246` + `controller.py:47-78` + 前端 `agent.ts:40-52` | `ai_agent_categories` 独立分类体系**疑似遗留死代码**（工作台已用 `ai_workspace_categories`） | 确认后下线或统一 |
| A6 | `logs_center/service.py:13-24` `_log_dict` | 调用日志明细 `page()/export()` 不返回 tokens/cost/reply_preview | 调用日志页无成本列 | `_log_dict` 带上，前端补列 |

### 🟢 低危

| # | 位置 | 问题 |
|---|------|------|
| A7 | `knowledge/search/agno_engine.py:66-78` | 注释「禁用自动建索引」与仍调用 `_create_vector_index` 矛盾，>2000 维退化顺序扫描 |
| A8 | `workflow/service.py:543-544` | 「取消」与「失败」都记为 error，错误率虚高 |
| A9 | `ontology/components/` 多个 + `workflow/NodeConfigPanel.vue` | 画布/表单内「删除/移除」无二次确认（需区分本地项 vs 实体删除） |
| A10 | `init_app.py:928,942` | 无代码应用与智能问数共用 `module_ai:query:ask`，权限粒度粗 |

---

## 五、优先处理建议（按「影响 × 通用性」排序）

1. **认证绕过/提权（最高优先）**：S1 auto-login 铸票无鉴权、S2 忘记密码无鉴权、S3 注册默认管理员。
2. **框架层数据权限缺口**：F1 写路径绕过数据权限、F5 树子节点绕过、F4/S5 多租户隔离未强制。
3. **敏感信息泄露**：S4 `/param/info` 无鉴权读 SMTP 密码/Webhook 密钥、F13 敏感配置明文。
4. **框架层 UI 骨架**：U1/U2/U3（PageContent 默认表格/分页/删除文案）——一次改动让所有 CRUD 页达标。
5. **框架层健壮性**：F2 异常泄露、F3 定时任务 exec RCE、F7 SSE 占连接、F10 多进程重复调度、A4 app.timeout 死字段。
6. **观测/成本**：A1/A2/A6 调用日志 tokens/cost 与列类型。
7. **收尾**：U4 全量 lint、U5 删除确认文案、A5 遗留死代码。
