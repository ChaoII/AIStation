# AI 集成开放平台 —— 开放面身份映射设计（阶段 B/C 前置）

> 关联 spec：`docs/superpowers/specs/2026-10-28-develop-capabilities-expansion.md`
> 问题：开放面 handler 用 `OPEN_AUTH = SimpleNamespace(user=None)` 调用平台 service 时，**多数 service 的
> create/update/delete 直接写 `auth.user.id`**（app/model/prompt/provider/knowledge/workflow/skill/tool/mcp/
> plugin/query 等），`user=None` → `AttributeError` → 500。且 `created_id` 是 FK 到 `sys_user.id`（PG 强制），
> 开放面写入归属必须指向**真实存在的** `sys_user` 行。

## 一、方案：开放平台服务账号身份映射

为开放面**幂等建立一个平台服务账号**（真实 `sys_user` 行，`is_superuser=True`），开放面所有写操作以它作为
`auth` 身份调用 service，使 `auth.user.id` 可用、`created_id/updated_id/deleted_id` 有合法归属，且超管
`is_superuser=True` 让权限过滤（`permission.py` 对 `user=None` 会做数据隔离降级）不再拦截开放面全局可见。

### 1. 服务账号
- **username**：`openai_platform`（唯一）。
- **password**：`PwdUtil.set_password_hash("openapi-service")`（永不登录，仅满足非空）。
- **name**：`开放平台服务账号`；**is_superuser**：`True`；**status**：`"0"`（正常）。
- **幂等**：按 `username` 查询，不存在才插入；首次在 `_ensure_open_service_user()` 惰性完成并缓存 `id`。

### 2. `open_auth()` 工厂（`handlers/_common.py`）
```python
async def open_auth() -> SimpleNamespace:
    uid = await _ensure_open_service_user()          # 幂等建账号 + 缓存 id
    return SimpleNamespace(user=SimpleNamespace(id=uid, is_superuser=True))
```
- 供所有开放面 handler 的 create/update/delete/toggle 等写操作调用 service 时使用。
- 只读/纯查询 handler 可继续用 `OPEN_AUTH`（`user=None`）或 `open_auth()`，二者都安全。

### 3. 改造范围
- **阶段 A**（app/model/prompt/provider/knowledge/workflow/cron）：把 create/update/delete/toggle 的
  `OPEN_AUTH` 改为 `await open_auth()`，**修复当前 `auth.user.id` 崩溃**。
- **新增品类**（skill/tool/mcp/plugin/query/ontology/sessions/space/market/dataset/overview/logs）：
  写操作一律 `await open_auth()`；显式收 `user_id` 的（如 `skill.delete(ids, user_id)`、`market.install(id, user_id)`）
  传 `auth.user.id`。

### 4. 归属与隔离语义
- 开放面创建的资产生成 `created_id = 服务账号 id`。**不按 app 隔离**（与阶段 A 各品类一致，由管理员按
  能力码授权到 app + 操作为平台级资产 + 敏感 op 审批）。
- **例外**（本次暂缓或仅开放只读）：`mcp`（原按 `created_id` 个人隔离）、`space`（原按 `user_id` + S3 key
  个人隔离）、`dataset`（CRUDBase 需 `auth.db`）。这些若开放写需按 `source_app_id` 或 `auth.db` 单独适配，
  记录到计划 B/C 的后续项；本次先开放「只读查询 / 平台级操作」中不依赖个人归属的部分。
- 真正的 **app 级审计** 由开放管道 `audit_call` 落 `ai_integration_call_logs`（appid + 能力码 + 结果），
  不与服务账号归属混淆。

## 二、落地改动面
- `backend/app/plugin/module_ai/develop/handlers/_common.py`：加 `open_auth()` / `_ensure_open_service_user()`。
- 阶段 A handler：`OPEN_AUTH` → `await open_auth()`（写路径）。
- 新增 handler：`skill.py` / `tool.py` / `mcp.py` / `plugin.py` / `query.py` / `ontology.py` / `sessions.py`
  / `space.py` / `market.py` / `dataset.py` / `overview_logs.py`，并在 `handlers/__init__.py` 挂载。
- `capabilities.py`：登记新品类与权限点；前端 `CATEGORIES` + i18n。

## 三、验收
- `open_auth()` 首次调用自动建服务账号且幂等；`created_id` 落库合法（不违反 FK）。
- 阶段 A 各品类 create/update/delete 不再因 `auth.user.id` 500（补测 create 路径）。
- 新增品类 handler 经 `registry.register` 校验（权限点合法）、`/ai/develop/capabilities` 返回、前端接入文档可见。
