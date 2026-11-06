# 资产嵌入令牌治理实施计划（生命周期 / 白名单 / 行为监管）

> 日期：2026-10-28
> 前置：`docs/superpowers/specs/2026-10-28-asset-token-governance-design.md`（已获用户认可）
> 范围：`backend/app/plugin/module_ai/asset_embed/` + 前端 `workspace/components/AssetEmbedDialog.vue` + `frontend/src/api/module_ai/assetEmbed.ts` + 12 语言 i18n + 后端测试。

## 决策（writing-plans 阶段，替代 spec 里留白处）

- **「永久」如何表达**：`AssetTokenIssueSchema` 增加 `permanent: bool = False`。`permanent=True` 时 `expires_at` 置为遥远未来 `datetime(2099, 12, 31, 23, 59, 59)`，**忽略 ttl**。`permanent=False` 时走 `clamp_asset_ttl(ttl)`（缺省仍 86400s、下限 60s、上限 2592000s，**上限保持不变**，只是不再作为「永久」的载体）。
  - 理由：现有 `ttl=None` 已语义为「缺省 24h」，若复用 `None`=永久会产生歧义（未传 ttl 的旧调用方会被当成永久）。用独立 `permanent` 布尔无歧义、向后兼容。
- **白名单校验纯函数**放 `service.py`（`PYTEST_NO_APP=1` 可测）。
- **更新令牌**：`allow_domains`/`allow_ips` 以「字段是否在 payload 中」区分（Pydantic `model_fields_set`）。字段**不在** payload = 不改；字段**出现**（含空串 `""`）= 设为该值（`""` 即清空为不限）。
- **客户端 IP 归一化**：`X-Forwarded-For` 首段（剥逗号 + 空格），为空回退 `request.client.host`。
- **白名单校验在 `row.use_count += 1` 之前**：被拒请求不累计使用次数。

---

## 任务一：后端模型 + schema_check 幂等建表

### 1.1 `backend/app/plugin/module_ai/asset_embed/model.py`
- `AiAssetAccessTokenModel` 增加两列（放在 `last_used_at` 之后）：
  ```python
  allow_domains: Mapped[str | None] = mapped_column(
      String(1024), default=None, nullable=True, comment="允许来源域名（逗号分隔，空=不限）"
  )
  allow_ips: Mapped[str | None] = mapped_column(
      String(1024), default=None, nullable=True, comment="允许来源IP/网段（逗号分隔，空=不限）"
  )
  ```
- `AiAssetEmbedLogModel` 增加两列（放在 `token_hash12` 之后）：
  ```python
  token_id: Mapped[int | None] = mapped_column(
      Integer, default=None, nullable=True, index=True, comment="关联 ai_asset_access_tokens.id"
  )
  client_ip: Mapped[str] = mapped_column(String(64), default="", nullable=False, comment="调用来源IP")
  ```

### 1.2 `backend/app/plugin/module_ai/asset_embed/schema_check.py`
- 在 `CREATE_ASSET_TOKENS_DDL` 的列清单里追加 `allow_domains VARCHAR(1024) DEFAULT NULL`、`allow_ips VARCHAR(1024) DEFAULT NULL`。
- 在 `CREATE_ASSET_LOGS_DDL` 的列清单里追加 `token_id INTEGER`、`client_ip VARCHAR(64) DEFAULT ''`。
- 新增两条幂等 ALTER，插到 `ensure_asset_embed_schema` 的 `ddl_statements` 列表（现有表补列，`IF NOT EXISTS` 幂等）：
  ```sql
  ALTER TABLE ai_asset_access_tokens ADD COLUMN IF NOT EXISTS allow_domains VARCHAR(1024);
  ALTER TABLE ai_asset_access_tokens ADD COLUMN IF NOT EXISTS allow_ips VARCHAR(1024);
  ALTER TABLE ai_asset_embed_logs ADD COLUMN IF NOT EXISTS token_id INTEGER;
  ALTER TABLE ai_asset_embed_logs ADD COLUMN IF NOT EXISTS client_ip VARCHAR(64) DEFAULT '';
  ```

完成标记：模型列可被 `test_asset_embed.py::test_asset_token_model_table` 断言到。

---

## 任务二：后端服务（service.py）

文件：`backend/app/plugin/module_ai/asset_embed/service.py`

### 2.1 常量与纯函数
- 新增常量 `ASSET_TOKEN_FOREVER_DATE = datetime(2099, 12, 31, 23, 59, 59)`。
- 新增 `parse_origin_host(value: str | None) -> str | None`：从 `Origin`/`Referer` 的 URL 提取 host（去协议、去路径、去端口）。用 `urllib.parse.urlparse`；无法解析返回 `None`。
- 新增 `match_whitelist(allow_domains: str | None, allow_ips: str | None, origin_host: str | None, client_ip: str) -> bool`：
  ```python
  def match_whitelist(allow_domains, allow_ips, origin_host, client_ip):
      def _split(v):
          return {x.strip().lower() for x in (v or "").split(",") if x.strip()}
      domains, ips = _split(allow_domains), _split(allow_ips)
      if not domains and not ips:
          return True                       # 两者都空 = 不限（兼容旧令牌）
      if origin_host and origin_host.lower() in domains:
          return True                       # 域名命中
      if client_ip and client_ip.lower() in ips:
          return True                       # IP 命中
      return False
  ```
- 新增 `extract_client_ip(request) -> str`：读 `request.headers.get("x-forwarded-for")` 首段，空回退 `request.client.host`（`getattr(request, "client", None)` 防御），再空返回 `""`。

### 2.2 `AssetTokenService.issue_token` 改签名
```python
@classmethod
async def issue_token(cls, kind, target_id, ttl=None, permanent=False,
                      allow_domains=None, allow_ips=None, issued_by="admin") -> dict:
```
- `expires_at = ASSET_TOKEN_FOREVER_DATE if permanent else (datetime.now() + timedelta(seconds=clamp_asset_ttl(ttl)))`。
- 落库时写 `allow_domains`、`allow_ips`。
- 返回值增加 `"permanent": bool(permanent)`；`expires_in` 在 permanent 时为 `None`。
- 现有 `test_asset_embed.py::test_clamp_ttl_bounds_and_default` 的 `clamp_asset_ttl` 语义**不变**，勿改。

### 2.3 `AssetTokenService.list_tokens`
- 每个 item dict 增加 `"allow_domains": r.allow_domains or ""`、`"allow_ips": r.allow_ips or ""`。

### 2.4 新增 `AssetTokenService.update_token`
```python
@classmethod
async def update_token(cls, token_id: int, allow_domains=None, allow_ips=None) -> bool:
```
- `allow_domains`/`allow_ips` 为 `None` 表示不改；否则写入（含清空为 `""`）。
- 取不到行 → 返回 `False`（控制器转 404）。

### 2.5 新增 `AssetTokenService.list_token_logs`
```python
@classmethod
async def list_token_logs(cls, token_id: int, page_no: int = 1, page_size: int = 20) -> dict:
```
- 查 `AiAssetEmbedLogModel` where `token_id == token_id` 且 `is_deleted == False`，`order_by(created_time.desc())`。
- 返回 `{"items": [...], "total": N, "has_next": bool, "page_no":..., "page_size":...}`。
- item 字段：`created_time`、`client_ip`、`result_status`、`error`、`latency_ms`、`message`、`sid`。
- `created_time` 用 `strftime("%Y-%m-%d %H:%M:%S")`（naive 本地时间，沿用项目惯例，**不**按调度器规则处理）。

---

## 任务三：后端鉴权白名单校验（auth.py）

文件：`backend/app/plugin/module_ai/asset_embed/auth.py`

- `EmbedContext` 增加 `client_ip: str` 字段（放在 `token_hash12` 后）。
- `get_embed_ctx` 签名改为 `async def get_embed_ctx(request: Request, authorization: str | None = Header(None))`。导入 `from fastapi import Header, Request`。
- 在校验链「目标存在且启用」之后、`row.use_count += 1` 之前插入：
  ```python
  origin_host = parse_origin_host(request.headers.get("origin") or request.headers.get("referer"))
  client_ip = extract_client_ip(request)
  if not match_whitelist(row.allow_domains, row.allow_ips, origin_host, client_ip):
      raise CustomException(msg="来源不在白名单", code=10403, status_code=403)
  ```
- `EmbedContext(...)` 构造增加 `client_ip=client_ip`。
- 注意：`/sdk.js` 不走 `get_embed_ctx`，无需处理。

---

## 任务四：后端行为监管（embed.py）

文件：`backend/app/plugin/module_ai/asset_embed/embed.py`

- `_write_log` 的 `AiAssetEmbedLogModel(...)` 增加：
  ```python
  token_id=ctx.token_id,
  client_ip=ctx.client_ip,
  ```
- `run_stream` 内部无其他改动（`ctx` 已带 `client_ip`）。

---

## 任务五：后端控制器（controller.py）

文件：`backend/app/plugin/module_ai/asset_embed/controller.py`

### 5.1 schema.py 增加两个 schema
- `AssetTokenIssueSchema` 增加：
  ```python
  permanent: bool = Field(default=False, description="是否永久（true 时忽略 ttl）")
  allow_domains: str | None = Field(default=None, max_length=1024, description="允许来源域名（逗号分隔，空=不限）")
  allow_ips: str | None = Field(default=None, max_length=1024, description="允许来源IP/网段（逗号分隔，空=不限）")
  ```
- 新增 `AssetTokenUpdateSchema`：
  ```python
  class AssetTokenUpdateSchema(BaseModel):
      allow_domains: str | None = Field(default=None, max_length=1024, description="允许来源域名")
      allow_ips: str | None = Field(default=None, max_length=1024, description="允许来源IP/网段")
  ```
  （用 `model_fields_set` 区分「未传=不改」。）

### 5.2 `issue_asset_token`
- 调用 `AssetTokenService.issue_token(..., ttl=data.ttl, permanent=data.permanent, allow_domains=data.allow_domains, allow_ips=data.allow_ips, issued_by="admin")`。

### 5.3 新增两个端点
- `PUT /asset-embed/tokens/{token_id}`（summary=更新令牌白名单）：
  ```python
  @AssetTokenRouter.put("/tokens/{token_id}", summary="更新令牌白名单")
  async def update_asset_token(token_id: int, data: AssetTokenUpdateSchema,
        _auth=Depends(AuthPermission(["module_ai:asset_embed:manage"]))) -> SuccessResponse:
      fields = data.model_fields_set
      allow_domains = data.allow_domains if "allow_domains" in fields else None
      allow_ips = data.allow_ips if "allow_ips" in fields else None
      if not await AssetTokenService.update_token(token_id, allow_domains, allow_ips):
          raise CustomException(msg="令牌不存在", code=10404, status_code=404)
      return SuccessResponse(data=None, msg="更新成功")
  ```
- `GET /asset-embed/tokens/{token_id}/logs`（summary=令牌使用日志）：
  ```python
  @AssetTokenRouter.get("/tokens/{token_id}/logs", summary="令牌使用日志")
  async def list_token_logs(token_id: int, page_no=1, page_size=20,
        _auth=Depends(AuthPermission(["module_ai:asset_embed:manage"]))) -> SuccessResponse:
      result = await AssetTokenService.list_token_logs(token_id, page_no=page_no, page_size=page_size)
      return SuccessResponse(data=result, msg="查询成功")
  ```
  - `page_no`/`page_size` 用 `Query(ge=1)`；`page_size` `Query(ge=1, le=100, default=20)`。

---

## 任务六：后端测试

### 6.1 `backend/tests/test_asset_embed.py`（`PYTEST_NO_APP=1` 纯逻辑）
- `test_clamp_ttl_bounds_and_default` 保持不动。
- 新增：
  - `test_parse_origin_host`：`https://a.com/x` → `a.com`；`http://a.com:8080/p` → `a.com`（忽略端口/路径）；`None`/非法 → `None`。
  - `test_match_whitelist`：
    - 两者都空 → True（不限）；
    - 域名命中（`allow_domains="a.com,b.com"`, origin=`b.com`）→ True；
    - IP 命中（`allow_ips="1.2.3.4"`, client=`1.2.3.4`）→ True；
    - 都不命中 → False；
    - 大小写/空格容忍。
  - `test_issue_token_model_columns`：`AiAssetAccessTokenModel` 含 `allow_domains`/`allow_ips`；`AiAssetEmbedLogModel` 含 `token_id`/`client_ip`（用 `__table__.columns` 断言）。

### 6.2 `backend/tests/test_asset_embed_run.py`（HTTP，扩展）
- 复用现有 `_issue` 帮助函数（改为可传 `permanent`/`allow_domains`/`allow_ips`，签名 `_issue(kind, target_id, ttl=None, permanent=False, allow_domains=None, allow_ips=None)`）。
- 新增用例：
  1. `test_run_whitelist_domain_403`：签发仅 `allow_domains="example.com"` 的令牌，不带来源头调用 → 403。
  2. `test_run_whitelist_domain_pass`：同令牌，带 `Origin: https://example.com` 调用 → 200。
  3. `test_run_whitelist_ip_pass`：签发仅 `allow_ips="127.0.0.1"`（或 `X-Forwarded-For: 127.0.0.1` 命中）→ 200。
  4. `test_run_whitelist_empty_unbounded`：签发无白名单（NULL）→ 200（兼容旧令牌）。
  5. `test_audit_log_token_and_ip`：成功调用后轮询 `AiAssetEmbedLogModel`，断言 `row.token_id == token_id` 且 `row.client_ip != ""`。
  6. `test_update_token_whitelist`：`PUT /api/v1/ai/asset-embed/tokens/{id}`（用 `auth_headers`），改 `allow_domains` 后列表接口返回新值。
  7. `test_list_token_logs_pagination`：对某令牌先制造若干调用，再 `GET .../tokens/{id}/logs?page_no=1&page_size=5`，断言 `items`/`total`/`has_next` 结构且按时间倒序。
- 运行方式：`cd backend && $env:CAPTCHA_ENABLE="false"; .\.venv\Scripts\python.exe -m pytest tests/test_asset_embed.py tests/test_asset_embed_run.py -q`。

---

## 任务七：前端 API（`frontend/src/api/module_ai/assetEmbed.ts`）

- `issueAssetToken` 形参扩展：`data: { kind, target_id, ttl?: number; permanent?: boolean; allow_domains?: string; allow_ips?: string }`。
- 新增 `updateAssetToken(id: number, data: { allow_domains?: string; allow_ips?: string })` → `PUT ${API_PATH}/tokens/${id}`。
- 新增 `listAssetTokenLogs(id: number, params: { page_no: number; page_size: number })` → `GET ${API_PATH}/tokens/${id}/logs`。

---

## 任务八：前端 `AssetEmbedDialog.vue` 重构

文件：`frontend/src/views/module_ai/workspace/components/AssetEmbedDialog.vue`

### 8.1 去除占位
- 删除 `asset_embed_tokenHint` / `asset_embed_tokenHintDesc` 那段 `el-alert`（`<el-alert ... class="asset-embed-dialog__alert">` 整块）。

### 8.2 弹窗分层（三层）
把「嵌入形式」radio 改为顶部**页签**（`el-tabs`），三层：应用小的 `el-tabs` 或 `el-radio-group` + `v-show`。建议用三个字段切换（`section`）保持结构清晰，或 `el-tabs v-model="section"`：
1. **接入代码**（section=code）：沿用现有三种形式 radio + `pre` 高亮 + 复制按钮 + 「生成令牌」按钮（保留）。
2. **令牌管理**（section=tokens）：
   - 工具栏右侧「生成令牌」触发**子表单**（内层 `el-dialog` 或表单展开）：
     - **有效期** `el-select`：1 小时（3600）/ 24 小时（86400）/ 7 天（604800）/ 30 天（2592000）/ 永久（permanent=true）。
     - **白名单域名** `el-input`（可空，提示逗号分隔）。
     - **白名单 IP** `el-input`（可空）。
     - 确认提交 → `issueAssetToken` → 走既有 `reveal` 弹窗展示明文。
   - 令牌列表（保留 `el-table border stripe`），列增：**白名单**（`row.allow_domains`/`row.allow_ips`，空显示「不限」）；操作列增 **编辑白名单**（弹小子表单调 `updateAssetToken`）、**查看日志**（切换 section=logs）。
   - 吊销保留（二次确认，已有）。
3. **使用日志**（section=logs）：
   - 选中令牌后分页表格：时间 / 来源 IP / 结果 / 耗时 / 消息摘要。
   - 用 `el-pagination`（`layout="total, sizes, prev, pager, next"` + `background`，右对齐），`@current-change`/`@size-change` 刷新。
   - 空态 `<el-empty :image-size="80" description="暂无数据" />`。

### 8.3 状态与逻辑
- `section` ref；`mintForm` reactive `{ ttl, permanent, allow_domains, allow_ips }`；`logTokenId` ref + `logs` ref + `logPage`/`logSize` + `logTotal`。
- `loadTokenLogs()` 调 `listAssetTokenLogs`；切到 logs 且选了 token 时加载。
- 提交子表单：`permanent? { permanent:true, allow_domains, allow_ips } : { ttl, allow_domains, allow_ips }`。
- 样式：沿用 Element Plus / `--el-*`；弹窗宽度保持 640px；`el-form` + `label-width`（94px 同现有）。白色面板/表格规范遵循 AGENTS.md 探测验收。

---

## 任务九：i18n（12 语言）

文件：`frontend/src/lang/package/{zh-cn,zh-hant,en,es,fr,de,ja,ko,ru,th,vi,ar}/ai_workflow_develop_add.ts`

- **删除** `asset_embed_tokenHint`、`asset_embed_tokenHintDesc`（各语言）。
- **新增**键（各语言，含中文译文参考）：
  - `asset_embed_section_code`（接入代码）、`asset_embed_section_tokens`（令牌管理）、`asset_embed_section_logs`（使用日志）。
  - `asset_embed_ttl`（有效期）、`asset_embed_ttl_1h`（1 小时）、`asset_embed_ttl_24h`（24 小时）、`asset_embed_ttl_7d`（7 天）、`asset_embed_ttl_30d`（30 天）、`asset_embed_ttl_forever`（永久）。
  - `asset_embed_allowDomains`（白名单域名）、`asset_embed_allowIps`（白名单 IP）。
  - `asset_embed_whitelistPlaceholder`（逗号分隔，留空不限制）。
  - `asset_embed_editWhitelist`（编辑白名单）、`asset_embed_viewLogs`（查看日志）。
  - `asset_embed_clientIp`（来源 IP）、`asset_embed_result`（结果）、`asset_embed_latency`（耗时）、`asset_embed_noLogs`（暂无日志）。
  - `asset_embed_unbounded`（不限）。
  - `asset_embed_updateSuccess`（更新成功）、`asset_embed_updateFail`（更新失败）。
  - `asset_embed_mintFormTitle`（生成令牌）。
- 新增键按项目现有 12 语言翻译风格补齐；非中文语言给出对应翻译（可参考 en 为基准，其余语言参照同文件既有关键词的翻译风格填写）。

---

## 任务十：验证

1. 后端：跑 `test_asset_embed.py` + `test_asset_embed_run.py`（命令见 6.2）。
2. 后端全量回归（提交前）：`cd backend && $env:CAPTCHA_ENABLE="false"; .\.venv\Scripts\python.exe -m pytest -q -n 4`（若耗时长可只跑关联文件，但至少 `module_ai` 相关）。
3. 前端：`pnpm run type-check`、`pnpm run lint`。
4. 无头浏览器截图：三页签 ×（有数据态 + 空态）+ 弹窗各态 + 参照页一张，用模型自身读图与 `frontend/src/views/module_system/param/index.vue` 逐项核对（表格 border/stripe、空态、分页、白名单显示）。
5. 联调服务（后端 8002 / 前端 5183）**保持运行，不要主动关闭**；改后端代码须按 AGENTS.md 先杀干净再 `--no-reload` 重启并验证 `/openapi.json`。

---

## 提交拆分建议

避免一次大提交，按可独立验证的单元拆：
1. `feat(asset-embed): 令牌表/日志表增加白名单与token_id/client_ip列`（任务一）。
2. `feat(asset-embed): 签发支持有效期/永久/白名单，新增白名单校验与行为监管`（任务二~四）。
3. `feat(asset-embed): 新增令牌更新与日志查询端点`（任务五 + 任务六测试）。
4. `feat(asset-embed): 前端弹窗节点三层重构与i18n`（任务七~九）。
