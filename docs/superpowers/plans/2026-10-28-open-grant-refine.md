# 开放平台授权细化（能力码 + REST/MCP 出口分离）实施计划

对应方案 A+B：授权单位从「权限点」细化到「能力码」，并支持对每个授权能力
分别开放 **REST（API）** 与 **MCP（工具）** 出口，满足「按需授权、可计费计量」。

## 背景与目标

现状问题（已审查确认）：
- 应用授权单位是 `integration:*` 权限点，但权限点与能力**不 1:1**
  （`integration:agent:query` → `agent.list`+`agent.get`；`integration:chat:query` → `chat.sessions`+`chat.messages`）。
- REST 与 MCP 出口不分离：授权一个权限点，REST 端点与对应 MCP 工具**同时**放行。
- 无法做到「只开放某几个 MCP 工具」「只开放某几个 REST API」。

目标：
1. 应用授权存**能力码集合**（`capabilities`），可精细到单个能力。
2. 新增**出口控制**（`channels`），对每个授权能力可单独开放 `rest` / `mcp`。
3. 兼容存量数据（`capabilities` 里旧存的 `integration:*` 权限点自动展开为能力码）。
4. REST 与 MCP 各自按「能力码 + 出口」校验，未开放出口一律 403。

## 兼容策略（向后兼容）

- 读取：`resolve_capability_grants(row.capabilities)` —— 旧项 `integration:*` 展开为其下全部
  能力码；新项（能力码）原样保留；非法项丢弃。
- `channels` 为 `None`/缺失时 = 该能力支持的全部出口（`rest` 若 `cap.rest`；`mcp` 若 `cap.mcp_tool`）。
- 写入（create/update）：`capabilities` 存能力码；`channels` 存 `{code: ["rest","mcp"]}`。
- 旧应用（无 channels）行为不变：授权即全出口。

## 步骤

- [x] 1. registry.py：加 `all_capability_codes()`、`is_valid_capability_code(code)`、
        `capabilities_for_codes(codes)`；保留 `capabilities_for` 兼容（转发）。
- [x] 2. capabilities.py：加 `resolve_capability_grants(raw)`、`normalize_capability_grants(raw)`、
        `normalize_channels(grants, raw_channels)`（写侧净化）。
- [x] 3. model.py：`AiIntegrationAppModel` 加 `channels`（JSONB dict，nullable）。写幂等加列迁移
        （alembic，`has_table` + inspect 列判断），新库由 create_all 自动带列。
- [x] 4. auth.py：`AppContext` 加 `grants: set[str]` 与 `channels: dict`；鉴权构造处从
        `row.capabilities`+`row.channels` 归一；`require_app_perm` → `require_capability(ctx, code, channel)`。
- [x] 5. openapi.py：`invoke_capability` 改用 `require_capability(ctx, cap.code, channel)`，
        `channel = "rest" if method=="REST" else "mcp"`。
- [x] 6. mcp_server.py：`list_tools` 与 `_capabilities_resource` 改用授权能力码 + `mcp` 通道过滤；
        `McpAuthMiddleware` 构造 AppContext 带 grants/channels。
- [x] 7. service.py：`create_app`/`update_app` 归一 `capabilities`（能力码）+ `channels`；
        `_app_to_dict` 输出 `channels` 与授权能力明细。
- [x] 8. controller.py：开放面 `GET /ai/develop-api/capabilities` 与 `auth/verify` 适配 grants/channels。
- [x] 9. 前端 `develop/index.vue`：授权区改为按**能力**勾选 + 每能力「REST/MCP」出口复选框
        （数据来自管理面 capabilities 接口：code/name/category/rest/mcp_tool）；提交能力码 + channels。
- [x] 10. 测试：新增/调整 `test_develop_*`（授权细化、出口分离、旧数据兼容）；
        `ruff` + `pytest tests/test_develop_*`。
- [x] 11. 文档：`docs/ai-embed-and-open-api.md` 补「按需授权与出口控制」说明；type-check。

## 关键文件

- `backend/app/plugin/module_ai/develop/`：registry.py、capabilities.py、model.py、auth.py、
  openapi.py、mcp_server.py、service.py、controller.py、schema.py
- `backend/app/alembic/versions/`：新增加列迁移
- `frontend/src/views/module_ai/develop/index.vue`
- `docs/ai-embed-and-open-api.md`
- `backend/tests/test_develop_*.py`

## 验收标准

- 应用可只授权 `agent.list` 而不同时授权 `agent.get`。
- 对某能力可只开 `rest` 不开 `mcp`（反之亦然）；未开放出口调用返回 403。
- 存量（旧 `integration:*`）应用授权自动展开、行为不变。
- REST/MCP 调用审计、配额、计量不受影响；前端可勾选到能力与出口粒度。
