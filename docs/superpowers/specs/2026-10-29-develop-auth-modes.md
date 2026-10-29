# AI 集成开放平台 —— 三种接入授权模式设计（A/B/C）

> 关联 spec：`docs/superpowers/specs/2026-10-28-develop-capabilities-expansion.md`
>            `docs/superpowers/specs/2026-10-29-develop-open-identity.md`
> 现状：`backend/app/plugin/module_ai/develop/`（`auth.py` 开放面鉴权 / `service.py` 应用 CRUD / `registry.py` 能力注册表 / `handlers/*.py`）
> 问题背景：开放平台只有一个「应用（appid:appkey）+ 管理员发放」入口，无法覆盖三类真实接入场景。
> **本文档把三种接入授权模式边界锁死，各有明确存在的必要性，互不重叠、不能互相替代。**
> 现状机制确认：平台已有 `pyjwt`+`decode_access_token`+`OAuth2Schema`（`app/core/security.py`）、
> `oauth_service.py`（仅「对外第三方登录」，平台是 OAuth **client**）；C 模式需平台充当 **OAuth server**，属新增。

---

## 〇、一句话总览（锁死边界）

三种模式**共用同一套底座**（应用 / appid:appkey / 能力清单 / 配额 / 调用审计），
区别**只有一件事：数据（与操作）按「谁」过滤**。

| 模式 | 谁创建应用 | 应用绑定谁 | 1 应用服务几个用户 | 数据/操作按谁过滤 | 是否需要用户主动授权 | 典型场景 |
|------|-----------|-----------|-------------------|-------------------|----------------------|----------|
| **A · 管理员分配** | 管理员 | 不绑定用户 | 1 个接入方 | 平台级/应用级 | 不需要 | 平台给固定合作方发 key |
| **B · 用户自助申请** | **用户自己**（管理员审核） | 绑定 1 个用户（`owner_user_id`） | 1 个用户（可多应用） | **按 owner 用户** | 申请时同意一次 | 每个客户各管各的、查自己的数据 |
| **C · OAuth 2.1 用户委托** | 用户/第三方注册 | 不绑定死用户 | **很多用户** | **按 token 里的当前用户** | **每个用户每次都要授权** | 一个 AI 助手（外部第三方）服务全员 |

**三者存在的必要性（各自不可替代）**：
- **A**：平台**直接管控**对外合作方的能力与配额，不需平台用户身份。B/C 都无法替代「管理员不经过用户、直接给一个外部系统授权」的需求。
- **B**：**用户自己**可控、可自助、可审计自己的应用；「申请者角色」成为「应用能力上限」（防越权）。A 给不了自助，C 给不了「一人一应用、自己掌控」。
- **C**：接入方是**外部第三方**（如用户的个人 AI 助手，**没有、也不应在我们平台注册 appid**），靠**用户授权**代表用户访问。A/B 都要求「应用是我们平台创建的」，C 允许「应用在外部、只需用户授权」。

---

## 一、模式 A · 管理员分配（保留现状，本就是这样）

### 1.1 边界
- **主体**：平台管理员（具备 `module_ai:develop:*`）。
- **方式**：管理员在「应用管理」创建应用 → 生成 `appid:appkey` → 手动勾选能力清单 / 配额 → 发放给外部接入方。
- **绑定**：应用**不绑定任何平台用户**，`owner_user_id = null`，`source_type = "admin"`。
- **数据范围**：平台级 / 应用级（操作**平台共享资产**：模型、供应商、技能池等）。

### 1.2 场景
平台与**固定合作方**对接，由平台统一授权、统一管控。合作方没有平台账号，只拿 key 调用。

### 1.3 实现（已在）
- `service.create_app` / `update_app` / `reset_appkey`（`owner_user_id` 留空即可）。
- 无需改动，**仅统一 `owner_user_id` 字段语义**（`null` = 平台级）。

---

## 二、模式 B · 用户自助申请（新增）

### 2.1 边界（与 A / C 的硬区分）
- **主体**：**平台注册用户**（普通用户，非管理员）。
- **方式**：用户登录平台后，在「开放平台 → 我的应用」**自助申请** appid/appkey（**须管理员审核**）。
- **绑定**：应用**绑定该用户**（`owner_user_id = auth.user.id`），`source_type = "self"`。
- **数据范围**：只返回**该用户自己拥有的**数据（`WHERE created_id/owner = 当前用户`）。
- **能力上限**：用户给应用勾选的能力，**不能超过该用户自身平台角色已有权限**（防越权提权）。
- **基数**：**用户 1—N 应用**（一个用户可申请多个 appid，各自独立凭证/能力/配额，查的都是该用户数据）。

### 2.2 场景
「**每个客户一个/多个应用、各管各的**」——用户查自己在平台上的知识库、技能、智能体、数据，或让外部系统接入自己的数据。

### 2.3 关键校验（防越权，必做）
```
用户勾选能力码（如 knowledge.delete）
   → 映射该能力码对应的平台权限点（module_ai:knowledge:delete）
   → 校验该用户角色的权限集合是否包含
        ✅ 包含 → 允许授权给应用
        ❌ 不包含 → 拒绝：「你无此权限，无法为应用申请该能力」
```

### 2.4 实现要点
- 新增**自助申请端点**（走平台用户 `auth.user.id`，非开放面服务账号）：`POST /ai/develop/self-apps`。
- 申请写入**待审核**（复用 `approvals` 审批流）或新增应用审核表；管理员批准 → 生成 `appid/appkey`、`source_type="self"`、`owner_user_id`。
- `AiIntegrationAppModel` 增 `owner_user_id`（FK sys_user，可空：空=平台级/A，非空=用户级/B）。
- **能力上限校验**：申请与后续更新应用能力清单时统一走 `assert_user_can_grant(user, perms)`。
- **数据过滤**：各 handler 的 list/get/delete 对 B 应用按 `owner_user_id` 过滤；对 A 应用保持平台级（或按权限策略）。

---

## 三、模式 C · OAuth 2.1 用户委托（新增）

### 3.1 边界（与 A / B 的硬区分）
- **主体**：**任意外部第三方 MCP 客户端**（个人 AI 助手，如用户的 walk 巴蒂等，**不注册在我们平台**）。
- **方式**：用户用外部助手发起 → 跳转**本平台授权页** → 用户登录并**同意授权** → 平台签发「代表该用户」的 access token → 助手持 token 调本平台 MCP/REST。
- **绑定**：应用**不绑定死用户**；「当前用户」由**每次请求携带的 token** 决定。
- **数据范围**：按 **token 里 `sub`（当前用户）** 过滤（`WHERE user_id = token.sub`）。
- **授权粒度**：用户授权时勾选**能力范围（scope）+ 有效期**；可随时撤销。
- **基数**：**应用 1—N 用户**（一个助手同时服务多个用户，各按各的授权）。

### 3.2 场景
「**一个外部 AI 助手服务公司全员**」——助手替 A 查考勤、替 B 发邮件、替 C 走审批，**各按各的权限**。A/B 都做不了（它们要求应用必须是我们平台创建的、且绑定单一用户）。

### 3.3 流程（OAuth 2.1 授权码 + 用户委托）
```
① 用户在外部助手发起 → 助手跳转 <host>/ai/develop/oauth/authorize?client_id=..&scope=..&redirect_uri=..&state=..
        ↓
② 用户在本平台登录 → 授权页展示「该助手将代表你访问：考勤/出差/邮件/审批」
        ↓
③ 用户同意 → 平台返回 authorization code 到 redirect_uri（携带 state 防 CSRF）
        ↓
④ 助手用 code 调 <host>/ai/develop/oauth/token 换取 access token（+ refresh token）
        ↓
⑤ 助手每次调 MCP/REST 携带 `Authorization: Bearer <user access token>`（+ 客户端 appid:appkey 双凭证）
        ↓
⑥ 本平台 MCP server 解 token → 取 `sub` = 当前用户身份 + scope → 按该用户权限过滤数据/校验操作
        ↓
⑦ token 过期 → 助手用 refresh token 静默续期（用户无需重新授权）
```

### 3.4 实现要点
- **平台充当 OAuth server**（新增，区别于已有 `oauth_service.py` 的「对外第三方登录 client」）。
- 新增表：`ai_integration_oauth_clients`（外部客户端注册或临时 client）、`ai_integration_oauth_tokens`（access/refresh，只存散列）。
- token 复用平台 JWT 底座（`pyjwt`、`JWTPayloadSchema`、`decode_access_token`），`sub` = 平台用户 id，`scope` = 授权能力码集合，`is_refresh` 语义区分。
- 新增端点：`/oauth/authorize` / `/oauth/token` / `/oauth/revoke`。
- **数据/操作过滤**：MCP server 与 REST 统一在 handler 前按 `token.sub`（用户）+ `scope`（能力）双重校验；敏感操作（发文/审批）额外校验该用户角色权限。
- **安全**：`state` 防 CSRF、`redirect_uri` 白名单、token 只存散列、支持撤销、`PKCE`（公共客户端必选）。

---

## 四、三模式的实现分层（避免揉在一起）

```
                    ┌─────────────────────────────────────────┐
                    │         共用底座（三模式复用）             │
                    │  应用 / appid:appkey / 能力清单 / 配额 /  │
                    │  调用审计 / REST+MCP 出口                  │
                    └─────────────────────────────────────────┘
                                     │
        ┌────────────────────────────┼────────────────────────────┐
        │                            │                            │
   [范围①] 按 owner/平台级        [范围②] 按 token 当前用户
   A (owner=null) + B (owner=user)   C (sub=token.sub)
```

- **底座**：`AiIntegrationAppModel` 增 `owner_user_id`；`auth.py` 增身份解析。
- **A**：`owner_user_id = null`（现状）。
- **B**：`owner_user_id = user.id` + 自助申请/审核 + 能力上限校验 + 按 owner 过滤。
- **C**：**不依赖 B 的 owner**，独立走 OAuth server + 按 token 过滤。

> 三模式在**同一个能力点**上可能并存（如 `agent.list` 既能被 A 应用调、也能被 B 应用调、也能被 C 的委托 token 调），
> 区分的是「**当前调用主体 → 数据范围**」，不是改能力本身。

---

## 五、资源公开治理（模式 B 数据可见性，2026-10-29 增补）

> 模式 B 数据过滤的**判定标准**（用户确认）：用户能看到「**自己创建的 + 平台共享的 + 主动公开的**」，
> 看不到「**其他用户未公开的私有资源**」。差一个统一的「资源可见性」模型，避免逐品类硬编码。

### 5.1 资源可见性三分来源（并集）

| 来源 | 判定 | 说明 |
|------|------|------|
| ① 自己创建的 | `created_id = owner用户` | B 用户自己建的资源 |
| ② 平台共享 | `created_id ∈ {超管, 平台服务账号}` | 超管/平台服务账号建的资源默认公开 |
| ③ 主动公开 | 资源 `is_public=true` | 用户主动公开（**默认不公开**，公开需走申请） |

**排除**：其他普通用户且 `is_public=false` 的资源。

### 5.2 `is_public` 语义与默认

- **超管/平台服务账号**创建的资源：`is_public=true`（**默认公开**，平台共建共享）。
- **普通用户**创建的资源：`is_public=false`（**默认不公开**，仅自己可见）。
- 个人想把资源**公开** → 提交「公开申请」→ 管理员审核（内容合规）→ 通过后置 `is_public=true`。
- 能力市场商品：天然公开（`is_public` 由市场语义保证，入驻即公开）。

### 5.3 公开申请 + 审核

- 新增 `ai_resource_public_auth`（资源公开授权表）：resource_type / resource_id / applicant_id /
  apply_status(pending/approved/rejected) / reviewed_by / reviewed_at / review_note / public_perm。
- 个人对私有资源发起公开申请 → 管理员审核 → 通过后写回资源 `is_public=true`，并记录公开权限
  （`public_perm`，默认 `readonly` 只读）。
- **自动审核机制（可选）**：对符合白名单条件（如资源类型/内容安全校验通过）的申请可自动通过，
  由配置开关 `RESOURCE_PUBLIC_AUTO_AUDIT` 控制；否则走人工审核。

### 5.4 公开后的访问权限

- 公开资源默认 **`readonly`（只读）**：其他用户/应用可**查**（list/get/检索），**不可改**（update/delete）。
- 后续可扩展 `public_perm ∈ {readonly, read_write}`，公开授权时指定；写操作按 `public_perm` 校验。

### 5.5 落地

- 各资源模型（agent/workflow/knowledge/model/prompt/provider/cron/skill/tool/plugin/mcp）增
  `is_public`（bool，默认按创建者角色：超管true/普通false）+ `lambda` 在 service 层过滤。
- service 层 `list` 加可选 `visible_user_ids` / `include_public` 入参，SQL 层 `WHERE
  (created_id=owner OR created_id IN(共享) OR is_public=true)`，A/C 不传即维持现状。
- 新增公开申请端点（用户侧提交 / 管理侧审核）与 `is_public` 开关。
- 超管默认公开：创建时按 `auth.user.is_superuser` 或是否服务账号置 `is_public`。

---

## 六、验收标准

1. **A**：管理员建应用（owner 空）→ 外部拿 key 调，平台级资产可见。
2. **B**：用户自助申请 → 管理员审核 → 发放 → 应用绑 owner → **只查「自己+平台共享+主动公开」**；
   **申请超出用户角色权限的能力被拒绝**（防越权）。
3. **C**：外部助手走授权码 → 用户同意 → 拿 token → 调 MCP 只返回 `sub`（该用户）数据；敏感操作按用户角色校验；可撤销。
4. 三种模式**同走一个能力注册表与调用审计**，无独立重复实现。
5. **资源公开治理**：超管创建默认公开；个人默认不公开；公开走申请审核；公开资源只读。
6. 后端测试覆盖三种模式的授权/越权/审计。

---

## 七、实施顺序

> 按依赖与成本递增，逐阶段实现；每个阶段独立可交付、可验收。

- **阶段 1（先做）**：模式 B（加上 A 的 `owner_user_id` 语义统一）。
  - 依赖：`owner_user_id` 字段、自助申请端点、应用审核、能力上限校验。**已完成**。
- **阶段 1.5（当前）**：资源公开治理（`is_public` + 平台共享/主动公开过滤 + 公开申请审核）。
  - 依赖：各资源模型加 `is_public`、service 层可见性过滤、公开申请表/端点。
  - 顺序：先做超管默认公开 + 平台共享过滤（不引入 is_public 即可跑通），再加 is_public + 公开申请审核。
- **阶段 2（再补）**：模式 C（OAuth 2.1 用户委托 server）。
  - 依赖：OAuth server 端点、client/token 表、token 解析 + 按 `sub` 过滤、PKCE/撤销。
- **A 全程保留**，不另起实现。
