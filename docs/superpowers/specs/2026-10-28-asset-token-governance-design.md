# 资产嵌入令牌治理设计（生命周期 / 白名单 / 行为监管）

> 日期：2026-10-28
> 范围：`backend/app/plugin/module_ai/asset_embed/` + 前端 `workspace/components/AssetEmbedDialog.vue` + 12 语言 i18n
> 前置：`docs/superpowers/specs/2026-10-28-embed-asset-design.md`（嵌入域归位，已实现）。本文为在其上新增的**令牌治理**增量设计。

## 一、背景与问题

嵌入域已实现「三种方式（聊天气泡 / iframe / 运行 API）共用同一个 `Bearer <asset_token>`」。但当前令牌机制偏薄，缺乏治理能力：

1. **申请令牌无超时选择**：前端「生成令牌」固定默认 24h，不能选有效期档位。
2. **无放行白名单**：任何拿到令牌的调用方都能调用，无法做到「只允许我指定的网站 / IP」。
3. **行为监管弱**：调用日志（`ai_asset_embed_logs`）未关联到具体令牌、未记录来源 IP，无法回答「这个 token 被谁、何时、调了几次、成没成」。
4. **界面有占位文案**：「凭证说明」整段纯说明文字与嵌入域语义不符（仍残留 appid/appkey 换票表述），占用弹窗空间。

## 二、目标

把资产令牌做成**可治理的令牌体系**：

- **统一令牌**：三种方式共用同一种令牌（现状，保留）。
- **生命周期**：申请时可选有效期档位；可手动吊销；列表展示使用次数 / 最后使用时间。
- **放行白名单**：每个令牌可配「域名」+「IP」白名单，任一匹配放行；不在名单 403。
- **行为监管**：每次调用落库并关联具体令牌 + 来源 IP；前端可按令牌查看使用日志。
- **界面重构**：去除占位的「凭证说明」；弹窗分层为「接入代码 / 令牌管理 / 使用日志」。

## 三、设计取舍（已与需求方确认）

- **嵌入形式不再细分**（bubble / iframe / api 不在日志中区分）。三种方式都凭同一 `Bearer <token>`，**所有调用天然都是「嵌入调用」**。遵循 YAGNI，砍掉按 `Origin/Referer` 推断形式的逻辑。
- **白名单 = 域名 + IP 双维度，任一匹配放行**。
  - 带 `Origin/Referer` 的页面嵌入（iframe / 气泡）→ 校验**域名**。
  - 服务端 `curl`（运行 API）无来源头 → 走 **IP** 白名单。
  - 域名、IP 都配了，任一命中即放行；**两者都为空 = 不限制**（兼容旧令牌）。
  - 不在白名单 → 403。
- **域名/IP 均可为空**：空 = 该维度不限。

## 四、数据模型改动

### 4.1 `ai_asset_access_tokens`（令牌表，新增列）

```
allow_domains  VARCHAR(1024) DEFAULT NULL   -- 逗号分隔的允许来源域名（可空=不限）
allow_ips      VARCHAR(1024) DEFAULT NULL   -- 逗号分隔的允许 IP/网段（可空=不限）
```

- 迁移方式：沿用 `schema_check.ensure_asset_embed_schema()` 的**幂等**方式，新增对这两个列的 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`（PostgreSQL）。**不走 alembic autogenerate**（项目惯例）。
- 已有令牌这两个列为 `NULL` → 视为「不限」（向后兼容，行为不变）。

### 4.2 `ai_asset_embed_logs`（调用日志表，新增列）

```
token_id   INTEGER DEFAULT NULL   -- 关联 ai_asset_access_tokens.id（此前为 NULL）
client_ip  VARCHAR(64) DEFAULT '' -- 调用来源 IP
```

- 幂等建表 DDL 同步补充这两列（含 `ADD COLUMN IF NOT EXISTS`）。
- 保留原 `token_hash12`（脱敏标识）以兼容历史行。

## 五、后端改动

### 5.1 签发（`AssetTokenService.issue_token` / `AssetTokenIssueSchema`）

- `AssetTokenIssueSchema` 增加：
  - `ttl: int | None`（有效期秒数）。档位与秒数对应：1 小时 = 3600，24 小时 = 86400，7 天 = 604800，30 天 = 2592000。
  - `allow_domains: str | None`、`allow_ips: str | None`。
- **「永久」档位**：后端 `clamp_asset_ttl` 当前上限 30 天。为支持「永久」，将其改为：`ttl=None` 表示永久（`expires_at` 置为遥远的 2099-12-31，或以专门标志表达）；`ttl=86400` 等显式秒数仍走 clamp。**具体实现以 writing-plans 阶段确定，spec 定为「永久 = 无过期」**。
- `issue_token` 落库时写 `allow_domains` / `allow_ips`。

### 5.2 白名单校验（`get_embed_ctx` 鉴权链）

在散列查令牌 → 未吊销未过期 → 目标存在启用 之后，**新增白名单校验**：

```
allow_domains / allow_ips 均空 → 放行（不限）
否则：
  origin_host = 解析请求头 Origin/Referer 的 host（若无则 None）
  域名命中 = origin_host 非空且 ∈ allow_domains
  ip 命中    = client_ip ∈ allow_ips
  任一命中 → 放行；否则 → 403
```

- 需要让 `get_embed_ctx` 拿到 `Request`（读取 `Origin`/`Referer`/`client.host`）。当前签名只有 `authorization` 头，需扩展为 `request: Request` + 头。
- 来源 IP 归一化：取 `X-Forwarded-For` 首段（有代理时）或 `request.client.host`。
- 403 用 `CustomException(msg="来源不在白名单", code=10403, status_code=403)`。

### 5.3 行为监管（日志写入）

- `run_stream` 的 `_write_log` 增加：`token_id=ctx.token_id`、`client_ip=ctx.client_ip`。
- `EmbedContext` 增加 `client_ip` 字段（鉴权时填充）。

### 5.4 新端点（管理面）

- `GET /ai/asset-embed/tokens/{id}/logs` —— 某令牌的使用日志（分页：`page_no`/`page_size`，返回 `{items,total,has_next}`；按 `created_time` 倒序）。
- `PUT /ai/asset-embed/tokens/{id}` —— 更新令牌（修改 `allow_domains` / `allow_ips`；也可用于续期，本期**只改白名单**）。
- `GET /ai/asset-embed/tokens` 列表返回增加 `allow_domains` / `allow_ips`（供前端回填展示）。

### 5.5 权限

沿用 `AuthPermission(["module_ai:asset_embed:manage"])`（既有）。白名单编辑 / 日志查看同权限码。

## 六、前端改动（`AssetEmbedDialog.vue`）

### 6.1 去除占位
- 删除 `asset_embed_tokenHint` / `asset_embed_tokenHintDesc` 那一段「凭证说明」`el-alert`（整段移除，不占空间）。

### 6.2 弹窗分层
1. **接入代码**：三种形式 tab（聊天气泡 / iframe / 运行 API）+ 复制按钮 + 语法高亮（已有，保留）。
2. **令牌管理**：
   - 「生成令牌」弹出一个小子表单：**有效期**（下拉：1 小时 / 24 小时 / 7 天 / 30 天 / 永久）+ **白名单域名** + **白名单 IP**（均可空）。
   - 令牌列表列：签发人 / 过期时间 / 使用次数 / 状态 / 白名单 / 操作（吊销）。
   - 操作新增：**编辑白名单**（生成后再改）、**查看日志**。
3. **使用日志**：选中令牌 → 分页表格（时间 / 来源 IP / 结果 / 耗时 / 消息摘要）。

### 6.3 样式
- 沿用 Element Plus / `--el-*`；弹窗宽度 640px；表单 `el-form` + `label-width` 与同模块一致。
- 删除类操作（吊销）二次确认（已有）。

## 七、i18n

- 新增 `asset_embed_*` 键：有效期档位（`ttl_1h`/`ttl_24h`/`ttl_7d`/`ttl_30d`/`ttl_forever`）、白名单域名 / IP 标签、编辑白名单、查看日志、来源 IP、白名单命中等。
- 12 语言（zh-cn / zh-hant / en / es / fr / de / ja / ko / ru / th / vi / ar）同步补充（本次只涉及少量新增键）。
- 删除占位的 `asset_embed_tokenHint` / `asset_embed_tokenHintDesc`（若前端已完全不引用，可从语言文件移除；否则保留无引用键亦可）。

## 八、测试

后端（`backend/tests/test_asset_embed.py` 扩展）：
- 签发时写 `allow_domains` / `allow_ips`。
- 白名单校验：域名命中放行 / IP 命中放行 / 都空不限 / 都不命中 403。
- 日志写入关联 `token_id` + `client_ip`。
- 日志查询端点分页与按令牌过滤。
- 更新令牌白名单。
- 兼容：旧令牌（`allow_domains`/`allow_ips` 为 NULL）不限。

前端：`vue-tsc` / `eslint` 通过；无头浏览器截图核对与参照页一致性。

## 九、验收标准

1. 生成令牌可选有效期档位与白名单（域名 / IP）。
2. 不在白名单的调用（含页面嵌入与运行 API）返回 403；空白名单向后兼容不限。
3. 令牌列表展示使用次数、最后使用时间、白名单；可编辑白名单、可吊销（二次确认）。
4. 可查看某令牌的使用日志（时间 / 来源 IP / 结果 / 耗时 / 消息摘要）。
5. 弹窗无「凭证说明」占位文案，布局分层清晰。
