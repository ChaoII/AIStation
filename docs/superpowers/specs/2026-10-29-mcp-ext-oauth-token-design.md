# AI 集成开放平台 —— 阶段 3b：MCP 复用外部 OAuth token 层设计

> 前置：阶段 3a `docs/superpowers/specs/2026-10-29-ext-oauth-client-design.md`（已实现，token 层就绪）。
> 本文档锁定**阶段 3b**：让 MCP 服务器也能像 http 工具那样，绑定一个「外部 OAuth 服务」，
> 当该 MCP 被 Agent 在某用户会话中装配建连时，自动注入该用户（= 创建者）对此外部服务的
> `Authorization: Bearer <access>` 头。**完全复用阶段 3a 的 token 层**（`ai_oauth_ext_tokens` +
> `resolve_ext_access_token`），不新建任何 token 表或刷新逻辑。

---

## 一、目标与边界（锁死）

**延续阶段 3a 的方向**：平台充当 OAuth `client`，平台内智能体/App 代平台用户访问外部第三方
OAuth 保护资源。阶段 3a 已实现 http 工具注入；阶段 3b 把同一能力落到 **MCP 服务器**。

**已确认决策（与用户逐节对齐）**：
1. **注入机制＝连接时注入**：MCP 的 `headers` 是建连（`connect`）时一次性传给 agno
   `MCPTools` 的静态配置，连接建立后该工具集被整个 Agent 会话共用。因此在 `build_mcp_tools`
   建连**前**，用当前用户的外部 access token 写入 `headers["Authorization"] = "Bearer <access>"`。
2. **绑定归属＝个人绑定，取创建者 token**：MCP 服务器是个人配置（`enabled_servers(ids, user_id)`
   已按 `created_id == user_id` 过滤），返回的服务器即创建者自己的。故建连时注入的就是**当前
   会话用户（= 创建者）**的 token，`user_id` 可直接用，无需区分创建者/会话用户。
3. **token 刷新＝建连前先 refresh 再注入**：建连前调用阶段 3a 的 `resolve_ext_access_token`，
   若 access 已过期则静默用 refresh 换新再注入。与 http 工具共用同一刷新逻辑。
4. **未绑定/未连接/取 token 失败＝跳过该 MCP 服务器（降级）**，不中断对话，与既有 MCP
   连接失败的降级语义一致。

**与阶段 3a 的关系**：3b 不涉及任何新 token 表、新刷新逻辑、新加密逻辑。唯一新增是
`AiMcpServerModel` 的绑定列 + `build_mcp_tools` 注入逻辑。

---

## 二、数据模型

### 2.1 `ai_mcp_servers` 增列

`AiMcpServerModel` 新增绑定列（FK 到阶段 3a 的服务表）：

| 列 | 类型 | 说明 |
|----|------|------|
| `oauth_ext_service_id` | Integer, FK `ai_oauth_ext_services.id`, null | 绑定的外部OAuth服务ID（MCP建连时注入Bearer） |

> 迁移为**追加列**（`has_column` 幂等守卫），在阶段 3a 迁移 `b8c9d0e1f2a3` 之后的 schema 上执行。
> revision `a3b4c5d6e7f8`，`down_revision='b8c9d0e1f2a3'`（当前唯一 head）。

---

## 三、服务逻辑

### 3.1 `mcp/schema.py`
`McpCreateSchema` / `McpUpdateSchema` 增加 `oauth_ext_service_id: int | None`。

### 3.2 `mcp/service.py`
- `_to_dict` 回显 `oauth_ext_service_id`（供前端配置回填）。
- `create` / `update` 写入/更新该列（与其它字段一致，仅显式传入时更新）。
- `enabled_servers` 无需改动（返回的 dict 已含 `_to_dict` 的全部字段，含新列）。

### 3.3 `mcp/tools.py` —— `build_mcp_tools(servers, user_id=None)`
签名扩展为接收 `user_id`。对每个服务器 dict：
- 若 `oauth_ext_service_id` 非空且 `user_id` 非空：
  - 调 `OAuthExtService.resolve_ext_access_token(service_id, user_id)` 取 access（内部过期自动 refresh）。
  - 成功则 `headers["Authorization"] = f"Bearer {access}"`（合并到已配置的 `headers` 上，不覆盖用户
    自定义的其它头）。
  - 取 token 失败（未连接/已撤销/刷新失败）→ `log.warning` 并**跳过该服务器**（返回的 tools 里不含它）。
- 否则（未绑定 / user_id 为空）保持原逻辑不变。

### 3.4 装配点（传 user_id）
- `agent/service.py` `_office_caps`（L202）：`build_mcp_tools(servers, user_id)`。
- `agent/service.py` agent 运行台（L1944）：`build_mcp_tools(servers, uid)`。

`connect_mcp_tools` 与 `run_agno_tool_stream` 无需改动——`headers` 已在 build 时注入，建连时直接用。

---

## 四、数据流

```
Agent 会话装配
  → _office_caps(row, user_id, ...) 或 agent 运行台(uid)
  → McpService.enabled_servers(mcp_ids, user_id)   # 已按 created_id==user_id 过滤
  → build_mcp_tools(servers, user_id)              # 绑定服务者调 resolve_ext_access_token 注入 Bearer
  → connect_mcp_tools(mcp_tools)                   # 建连（headers 已带 Authorization）
  → run_agno_core(extra_tools=connected_mcp)
```

---

## 五、错误处理

- 绑定服务但用户未连接 / 已撤销 / access 取不到 → 跳过该 MCP 服务器（降级），记 warning。
- 绑定服务但 `user_id` 为空（无会话用户）→ 退化为未绑定处理（不注入），保持可用。
- 建连本身失败仍走既有 `connect_mcp_tools` 的 try/except 跳过低级。

---

## 六、测试

1. **绑定服务 + 用户已授权**：`build_mcp_tools` 产出含 `Authorization: Bearer <access>` 的工具集。
2. **未绑定服务**：`build_mcp_tools` 产出不含 `Authorization` 的工具集（行为不变）。
3. **绑定服务但未连接/已撤销**：`resolve_ext_access_token` 抛错 → 该服务器被跳过（tools 不含它），
   不抛异常。
4. **回归**：既有 MCP CRUD / 连接测试不受影响。

---

## 七、YAGNI / 边界

- **不**新增前端配置界面（绑定列经管理接口暴露，前端配置留待后续，与阶段 3a 同思路）。
- **不**涉及 MCP 原生 OAuth（RFC 9728）——第三方 MCP 自身的鉴权不在平台代管范围。
- **不**改 `connect_mcp_tools` / `run_agno_tool_stream` / `_USER_ID_CTX`。
- token 生命周期完全复用阶段 3a 的 `ai_oauth_ext_tokens` 与刷新/撤销逻辑。
