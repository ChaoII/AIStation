# 问数权限：统一策略引擎 + SQL 收口（计划 A：P0-P2）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把问数的权限从"三套隐式规则 + 两处判定"改成"一处策略、一个网关、SQL 层确定性改写"，先止血（`SELECT *` 绕过、无主体执行），再具备行/列可控能力。

**Architecture:** 新增 `query/policy/` 子包：`model`（表与常量）→ `principal`（主体）→ `engine`（纯逻辑判定）→ `compiler`（sqlglot 改写）→ `guard`（编排 + 三态开关）→ `audit`（留痕）。`AiQueryService._execute_one` 是唯一收口，所有入口经它调用 `QueryGuard.prepare()`。

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy 2.0 async / sqlglot（已在依赖中）/ pytest（`PYTEST_NO_APP=1` 跑纯逻辑）

**Spec:** `docs/superpowers/specs/2026-11-06-query-permission-model-design.md`

## Global Constraints

- 提交信息与代码注释用中文；提交格式 `feat(query): ...` / `fix(query): ...`。
- **不要**用 `alembic autogenerate`：插件表在 `ensure_policy_tables()` 里幂等建表。
- 不新增第三方依赖（`sqlglot` 已在 `backend/pyproject.toml`）。
- PG 与 SQLite 双兼容：DDL 走 `_ddl_for_dialect()`；测试优先纯逻辑（`PYTEST_NO_APP=1`）。
- 本计划只改后端，不动前端；管理界面在计划 B。
- 权限判定 **fail-closed**；审计写入失败 **fail-open**（只记 warning，不影响查询）。
- 默认值：`POLICY_ENGINE=legacy`（本计划结束时默认仍为 `legacy`，由运维显式切 `shadow`）。

## Review Focus

1. `SELECT *` / `t.*` / 别名 / CTE 里的星号：必须**拒绝**（在含敏感列的表上），绝不能因为解析不到列而放行。
2. SQL 解析失败、未知方言、动态拼接（`EXECUTE`/`format()`）：必须 deny，不能抛未捕获异常，更不能放行。
3. 行策略引用的主体属性缺失（用户没有 `dept_id`）：必须按"条件不成立"拒绝该表，不能忽略条件。
4. 视图血缘只能映射到表、映射不到列：必须按 §5.4 三级降级，不能"假装加了行过滤"。
5. 审计写入异常：查询继续，但必须 `log.warning` 留痕；不允许把异常吞掉且无日志。

---

### Task 1: 策略数据模型与幂等建表

**Files:**
- Create: `backend/app/plugin/module_ai/query/policy/__init__.py`
- Create: `backend/app/plugin/module_ai/query/policy/model.py`
- Modify: `backend/app/plugin/module_ai/query/service.py:231`（`_ensure_query_tables()` 里追加调用）
- Test: `backend/tests/test_query_policy_model.py`

**Interfaces:**
- Consumes: `app.core.database.async_db_session`、`app.plugin.module_ai.query.service._ddl_for_dialect`
- Produces: `POLICY_TABLES_SQL: list[str]`、`async def ensure_policy_tables() -> None`、
  `async def sensitive_tables() -> set[str]`（查 `ai_query_asset_columns` 里 `sensitive=true` 的表名集合）

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_query_policy_model.py
from app.plugin.module_ai.query.policy.model import POLICY_TABLES_SQL

def test_policy_tables_cover_three_tables():
    joined = "\n".join(POLICY_TABLES_SQL).lower()
    assert "ai_policy" in joined
    assert "ai_query_access_log" in joined
    assert "ai_policy_shadow_diff" in joined
    assert "create table if not exists" in joined
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTEST_NO_APP=1 .venv/Scripts/python.exe -m pytest tests/test_query_policy_model.py -q`
Expected: FAIL（`ModuleNotFoundError: ...policy.model`）

- [ ] **Step 3: 实现**

`policy/model.py`：按 spec §4 的三张表写 `POLICY_TABLES_SQL`（PG 语法，建表用
`CREATE TABLE IF NOT EXISTS`），并提供：

```python
async def ensure_policy_tables() -> None: ...
```

实现方式复刻 `service._ensure_query_tables()`：逐条 `_ddl_for_dialect(sql)` +
`async_db_session.begin()`，异常走 `service._degrade("policy_tables", e)`（best-effort）。
在 `service._ensure_query_tables()` 末尾 `await ensure_policy_tables()`。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTEST_NO_APP=1 .venv/Scripts/python.exe -m pytest tests/test_query_policy_model.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/policy/__init__.py \
        backend/app/plugin/module_ai/query/policy/model.py \
        backend/app/plugin/module_ai/query/service.py \
        backend/tests/test_query_policy_model.py
git commit -m "feat(query): 策略/审计/shadow 三张表与幂等建表"
```

---

### Task 2: 统一主体 Principal

**Files:**
- Create: `backend/app/plugin/module_ai/query/policy/principal.py`
- Test: `backend/tests/test_query_policy_principal.py`

**Interfaces:**
- Consumes: `AiQueryService._user_role_codes(auth)`、`_is_superuser(uid)`（可 monkeypatch）
- Produces:
  ```python
  @dataclass(frozen=True)
  class Principal:
      user_id: int | None
      is_superuser: bool
      roles: tuple[str, ...]
      attrs: dict[str, str]
      entry: str

  async def load_principal(auth, entry: str = "ask") -> Principal | None
  ```

- [ ] **Step 1: 写失败测试（纯逻辑，monkeypatch 依赖）**

```python
def test_missing_auth_returns_none():
    assert asyncio.run(load_principal(None)) is None

def test_principal_carries_roles_and_attrs(monkeypatch):
    # monkeypatch 角色来源与属性来源，断言 Principal 字段
    p = asyncio.run(load_principal(fake_auth(uid=7), entry="cron"))
    assert p.user_id == 7 and p.entry == "cron"
    assert p.roles == ("ADMIN",)
    assert p.attrs.get("dept_id") == "3"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTEST_NO_APP=1 .venv/Scripts/python.exe -m pytest tests/test_query_policy_principal.py -q`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

`load_principal`：`auth` 为空 → `None`；`auth.user.id` → uid；`is_superuser` 取 `auth.user.is_superuser`；
`roles` 用现有 `_user_role_codes(auth)`；`attrs` 读取 `sys_user` 的 `dept_id`（列不存在则 `{}`，
异常记 `log.warning` 后返回 `{}`）。超管不跳过 attrs 加载（审计需要）。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTEST_NO_APP=1 .venv/Scripts/python.exe -m pytest tests/test_query_policy_principal.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/policy/principal.py backend/tests/test_query_policy_principal.py
git commit -m "feat(query): 统一 Principal（角色 + 属性 + 入口）"
```

---

### Task 3: 审计写入与解释查询

**Files:**
- Create: `backend/app/plugin/module_ai/query/policy/audit.py`
- Test: `backend/tests/test_query_policy_audit.py`

**Interfaces:**
- Produces:
  ```python
  def sql_hash(sql: str) -> str
  def sql_preview(sql: str, limit: int = 2048) -> str
  async def write_access_log(*, principal, entry: str, datasource: str, sql: str,
                             decision: str, reason: str, policy_ids: list[int],
                             rewrite: list[dict], elapsed_ms: int) -> None
  async def list_access_logs(limit: int = 100) -> list[dict]
  ```

- [ ] **Step 1: 写失败测试**

```python
def test_sql_hash_is_stable_and_normalized():
    assert sql_hash("SELECT 1") == sql_hash("  select   1  ")

def test_preview_truncates_and_masks_literals():
    s = sql_preview("select * from t where phone='13800138000'")
    assert "13800138000" not in s
    assert len(sql_preview("x" * 5000)) <= 2048

def test_write_failure_does_not_raise(monkeypatch):
    # monkeypatch 事务抛异常，断言不抛且调用 log.warning
    asyncio.run(write_access_log(principal=None, entry="ask", datasource="ds:4",
                                 sql="select 1", decision="permit", reason="",
                                 policy_ids=[], rewrite=[], elapsed_ms=1))
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTEST_NO_APP=1 .venv/Scripts/python.exe -m pytest tests/test_query_policy_audit.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

`sql_hash` = sha256（先 `" ".join(sql.split())` 归一化、转小写）；
`sql_preview` 用正则把单引号/双引号字面量替换为 `'?'`，再截断；
`write_access_log` 全程 try/except，异常只 `log.warning`（fail-open）。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTEST_NO_APP=1 .venv/Scripts/python.exe -m pytest tests/test_query_policy_audit.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/policy/audit.py backend/tests/test_query_policy_audit.py
git commit -m "feat(query): 权限审计写入（失败不影响查询）"
```

---

### Task 4: 判定引擎（纯逻辑）

**Files:**
- Create: `backend/app/plugin/module_ai/query/policy/engine.py`
- Test: `backend/tests/test_query_policy_engine.py`

**Interfaces:**
- Consumes: `Principal`（Task 2）
- Produces:
  ```python
  @dataclass(frozen=True)
  class Policy:
      id: int; effect: str; resource_kind: str; resource_code: str
      subject_kind: str; subject_value: str; condition: str
      columns: tuple[str, ...]; mask_expr: str; marking: str
      priority: int; enabled: bool

  @dataclass(frozen=True)
  class Decision:
      permit: bool; reason: str = ""; policy_ids: tuple[int, ...] = ()
      sql: str = ""; applied: tuple[dict, ...] = ()

  def decide_table(policies: list[Policy], principal: Principal, table: str) -> Decision
  def decide_column(policies: list[Policy], principal: Principal, table: str,
                    column: str) -> Decision   # mask 命中时 applied=[{"mask": expr}]
  ```

- [ ] **Step 1: 写失败测试（覆盖 spec §3.2 六条）**

```python
def test_default_deny_without_allow():
    assert not decide_table([], P(roles=("USER",)), "t").permit

def test_superuser_bypasses_but_reports_reason():
    d = decide_table([], P(is_superuser=True), "t")
    assert d.permit and "superuser" in d.reason

def test_deny_beats_allow():
    pol = [allow("t", "role", "USER"), deny("t", "role", "USER")]
    assert not decide_table(pol, P(roles=("USER",)), "t").permit

def test_mask_beats_allow_but_not_deny():
    pol = [allow("t", "role", "USER"), mask("t", "role", "USER", "phone", "LEFT(phone,3)")]
    d = decide_column(pol, P(roles=("USER",)), "t", "phone")
    assert d.permit and d.applied[0]["mask"] == "LEFT(phone,3)"

def test_most_specific_subject_wins():
    pol = [allow("t", "everyone", "", columns=("a", "b")),
           deny("t", "role", "USER", columns=("b",))]
    assert decide_column(pol, P(roles=("USER",)), "t", "a").permit
    assert not decide_column(pol, P(roles=("USER",)), "t", "b").permit

def test_missing_attr_makes_row_policy_deny():
    pol = [allow("t", "role", "USER", condition="dept_id = $attr.dept_id")]
    assert not decide_table(pol, P(roles=("USER",), attrs={}), "t").permit
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTEST_NO_APP=1 .venv/Scripts/python.exe -m pytest tests/test_query_policy_engine.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

按 spec §3.2：`deny > mask > allow`；同 effect 按主体具体性
`user > attr > role > domain > everyone`；同具体性 `priority` 降序；`allow` 并列取并集；
`condition` 里的 `$attr.x` 在 `principal.attrs` 缺失时视为不成立；超管返回
`Decision(True, reason="superuser bypass", policy_ids=())`。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTEST_NO_APP=1 .venv/Scripts/python.exe -m pytest tests/test_query_policy_engine.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/policy/engine.py backend/tests/test_query_policy_engine.py
git commit -m "feat(query): 策略判定引擎（deny>mask>allow + 默认拒绝）"
```

---

### Task 5: 星号止血（P0，安全修复）

**Files:**
- Create: `backend/app/plugin/module_ai/query/policy/star.py`
- Test: `backend/tests/test_query_policy_star.py`

**Interfaces:**
- Consumes: `sqlglot`
- Produces:
  ```python
  def unexpanded_star(sql: str, sensitive_tables: set[str], dialect: str = "postgres") -> str | None
  # 返回命中的表名；None = 无风险
  ```

- [ ] **Step 1: 写失败测试（4 条绕过写法）**

```python
def test_plain_star_on_sensitive_table_is_flagged():
    assert unexpanded_star("select * from fuel_price", {"fuel_price"}) == "fuel_price"

def test_qualified_star_is_flagged():
    assert unexpanded_star("select t.* from fuel_price t", {"fuel_price"}) == "fuel_price"

def test_star_on_safe_table_is_allowed():
    assert unexpanded_star("select * from dim_city", {"fuel_price"}) is None

def test_parse_failure_is_treated_as_risk():
    assert unexpanded_star("select * from ((((", {"fuel_price"}) == "*"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTEST_NO_APP=1 .venv/Scripts/python.exe -m pytest tests/test_query_policy_star.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

用 `sqlglot.parse_one` 找 `exp.Star`，回溯所在 `exp.Table`（别名要还原成真实表名）；
解析异常返回 `"*"`（调用方据此拒绝）。表名比较大小写不敏感。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTEST_NO_APP=1 .venv/Scripts/python.exe -m pytest tests/test_query_policy_star.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/policy/star.py backend/tests/test_query_policy_star.py
git commit -m "fix(query): 含敏感列的表禁止未展开星号（P0 安全止血）"
```

---

### Task 6: 唯一网关 QueryGuard（三态开关 + shadow）

**Files:**
- Create: `backend/app/plugin/module_ai/query/policy/guard.py`
- Test: `backend/tests/test_query_policy_guard.py`

**Interfaces:**
- Consumes: `load_principal`、`audit.write_access_log`、`star.unexpanded_star`、`engine`（Task 4）、
  `model.sensitive_tables`（Task 1）
- Produces:
  ```python
  async def prepare(*, sql: str, principal: Principal | None, entry: str,
                    datasource: str, dialect: str = "postgres",
                    legacy_check: Callable[[], Awaitable[Decision]] | None = None) -> Decision
  ```

> 星号止血（P0）**对三种模式都生效**：即使 `POLICY_ENGINE=legacy`，含敏感列的表出现
> 未展开星号也必须拒绝——否则 P0 等于没做。

- [ ] **Step 1: 写失败测试（开关三态 + 无主体）**

```python
def test_missing_principal_denies(monkeypatch):
    d = asyncio.run(prepare(sql="select 1", principal=None, entry="ask", datasource="ds:4"))
    assert not d.permit and "principal" in d.reason

def test_shadow_mode_returns_legacy_decision_but_records_diff(monkeypatch):
    # legacy 放行、新引擎拒绝 → 返回 permit，且 diff 被写入
    ...

def test_enforce_mode_returns_new_decision():
    ...

def test_legacy_mode_never_calls_engine():
    ...
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTEST_NO_APP=1 .venv/Scripts/python.exe -m pytest tests/test_query_policy_guard.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

读 `POLICY_ENGINE`（`AiQueryService._cfg()`，缺失默认 `legacy`）：
- `legacy`：只做"无主体拒绝 + 审计"，其余交给调用方 `legacy_check()`；
- `shadow`：新旧都算，写 `ai_policy_shadow_diff`，返回旧结论；
- `enforce`：返回新结论。
最后统一 `write_access_log`（fail-open）。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTEST_NO_APP=1 .venv/Scripts/python.exe -m pytest tests/test_query_policy_guard.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/policy/guard.py backend/tests/test_query_policy_guard.py
git commit -m "feat(query): QueryGuard 三态网关（legacy/shadow/enforce）"
```

---

### Task 7: 接入唯一收口 `_execute_one`

**Files:**
- Modify: `backend/app/plugin/module_ai/query/service.py:7753`（`_execute_one`）
- Test: `backend/tests/test_query_policy_wired.py`

**Interfaces:**
- Consumes: `policy.guard.prepare`、`policy.principal.load_principal`
- Produces: `_execute_one` 内新增 `entry` 关键字参数（默认 `"ask"`），供报表/指标/导出复用

- [ ] **Step 1: 写失败测试**

```python
def test_execute_one_calls_guard_with_principal(monkeypatch):
    # 桩住 guard.prepare，断言被调用且 entry 透传
    ...
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTEST_NO_APP=1 .venv/Scripts/python.exe -m pytest tests/test_query_policy_wired.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

在 `_execute_one` 的字段级 ACL 之前调用 `prepare(...)`；`legacy_check` 传入现有
`_ont_sql_violations` + `validate_sql` 组合，保证 `legacy` 模式行为不变。
`entry` 由调用方传入（`ask` / `report` / `metric` / `export` / `eval`）。

- [ ] **Step 4: 跑测试确认通过，且既有 ACL 测试不回归**

Run:
```
cd backend && PYTEST_NO_APP=1 .venv/Scripts/python.exe -m pytest tests/test_query_policy_wired.py tests/test_query_acl_single_choke.py tests/test_query_custom_ds_field_acl.py -q
```
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/service.py backend/tests/test_query_policy_wired.py
git commit -m "feat(query): _execute_one 接入 QueryGuard（唯一收口）"
```

---

### Task 8: 旧规则 backfill（含 legacy_default_allow）

**Files:**
- Create: `backend/app/plugin/module_ai/query/policy/backfill.py`
- Test: `backend/tests/test_query_policy_backfill.py`

**Interfaces:**
- Produces: `async def backfill_policies(dry_run: bool = False) -> dict`（返回各类计数）

- [ ] **Step 1: 写失败测试**

```python
def test_backfill_is_idempotent(fake_db):
    a = asyncio.run(backfill_policies())
    b = asyncio.run(backfill_policies())
    assert a["created"] > 0 and b["created"] == 0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTEST_NO_APP=1 .venv/Scripts/python.exe -m pytest tests/test_query_policy_backfill.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

按 spec §4.1 五行映射；`legacy_default_allow` 的 `name` 固定为
`"legacy_default_allow"`，重复执行按 name 判重；写入 `ai_policy_migration`。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTEST_NO_APP=1 .venv/Scripts/python.exe -m pytest tests/test_query_policy_backfill.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/policy/backfill.py backend/tests/test_query_policy_backfill.py
git commit -m "feat(query): 旧权限规则迁移（幂等 + 兜底 allow）"
```

---

### Task 9: SQL 编译器（行包装 / 列投影 / mask）

**Files:**
- Create: `backend/app/plugin/module_ai/query/policy/compiler.py`
- Test: `backend/tests/test_query_policy_compiler.py`

**Interfaces:**
- Consumes: `Decision`（Task 4）、`sqlglot`
- Produces:
  ```python
  @dataclass(frozen=True)
  class AccessPlan:
      row_filters: dict[str, str]                  # 表名 -> 谓词
      allowed_columns: dict[str, tuple[str, ...] | None]
      masked: dict[str, dict[str, str]]            # 表 -> {列: 掩码表达式}
      denied: dict[str, frozenset[str]]

  def build_plan(policies: list[Policy], principal: Principal,
                 tables: dict[str, list[str]]) -> AccessPlan
  def rewrite(sql: str, plan: AccessPlan, *, dialect: str = "postgres") -> Decision
  ```

- [ ] **Step 1: 写失败测试（单表 / join / 聚合 / 星号 / 别名）**

```python
def plan(**kw):
    """测试用简写：allowed -> allowed_columns。"""
    kw["allowed_columns"] = kw.pop("allowed", {})
    kw.setdefault("row_filters", {}); kw.setdefault("masked", {}); kw.setdefault("denied", {})
    return AccessPlan(**kw)

def test_row_filter_wraps_table():
    d = rewrite("select id from t", plan(row_filters={"t": "dept_id = 3"}))
    assert d.permit and "dept_id = 3" in d.sql

def test_star_expands_to_allowed_columns():
    d = rewrite("select * from t", plan(allowed={"t": ("a", "b")}))
    assert "a" in d.sql and "b" in d.sql and "*" not in d.sql

def test_denied_column_is_rejected():
    assert not rewrite("select phone from t", plan(denied={"t": {"phone"}})).permit

def test_internal_wrapper_star_is_not_rechecked():
    d = rewrite("select a from t", plan(row_filters={"t": "1=1"}, allowed={"t": ("a",)}))
    assert d.permit
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTEST_NO_APP=1 .venv/Scripts/python.exe -m pytest tests/test_query_policy_compiler.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

规则见 spec §5.2/§5.3：表引用包装、参数命名空间 `:p_policy_<n>`、星号按
`allowed_columns` 展开（`None` = 全部）、`masked` 替换投影、deny 列出现在任何位置
（投影/条件/排序）即拒绝；内部包装产生的星号用节点标记跳过列判定；解析失败 deny。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTEST_NO_APP=1 .venv/Scripts/python.exe -m pytest tests/test_query_policy_compiler.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/policy/compiler.py backend/tests/test_query_policy_compiler.py
git commit -m "feat(query): SQL 编译器（行包装 + 列投影 + 掩码）"
```

---

### Task 10: 视图按血缘三级降级

**Files:**
- Create: `backend/app/plugin/module_ai/query/policy/views.py`
- Test: `backend/tests/test_query_policy_views.py`

**Interfaces:**
- Consumes: `query/lineage.py` 的视图→基表映射
- Produces:
  ```python
  def resolve_view_policies(view: str, lineage: dict[str, list[str]],
                            policies: list[Policy]) -> tuple[AccessPlan, str]
  # 返回 (plan, tier)  tier ∈ {"column","table","none"}
  ```

- [ ] **Step 1: 写失败测试（三级各一条）**

```python
def test_column_level_mapping_applies_row_filter():
    plan, tier = resolve_view_policies("v_price", {"v_price": ["fuel_price"]}, pols)
    assert tier == "column" and "dept_id" in plan.row_filters["v_price"]

def test_table_only_mapping_keeps_table_deny():
    plan, tier = resolve_view_policies("v2", {"v2": ["fuel_price"]}, pols)
    assert tier == "table" and plan.row_filters == {}

def test_unmapped_view_with_protected_base_is_denied():
    plan, tier = resolve_view_policies("v3", {"v3": ["unknown"]}, pols)
    assert tier == "none"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTEST_NO_APP=1 .venv/Scripts/python.exe -m pytest tests/test_query_policy_views.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

三级：列可映射 → 精确套用；仅表可映射 → 只套表级 allow/deny（**不加**行条件）；
完全不可映射 → 血缘含受保护表则 deny，否则放行且 `tier="none"`（审计可见）。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTEST_NO_APP=1 .venv/Scripts/python.exe -m pytest tests/test_query_policy_views.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/policy/views.py backend/tests/test_query_policy_views.py
git commit -m "feat(query): 视图权限按血缘三级降级"
```

---

### Task 11: 绕过回归集（12 条）

**Files:**
- Create: `backend/tests/test_query_policy_bypass.py`
- Test: 同上

**Interfaces:**
- Consumes: `compiler.rewrite`、`AccessPlan`（Task 9）

- [ ] **Step 1: 写失败测试（12 条全列）**

```python
BYPASS_CASES = [
    ("select * from t", False),
    ("select t.* from t", False),
    ("select a from t", True),
    ("with x as (select * from t) select * from x", False),
    ("select * from t union select * from t", False),
    ("select (select phone from t limit 1) from t", False),
    ('select * from "t"', False),
    ("SELECT * FROM T", False),
    ("select /*x*/ * from t", False),
    ("select * from t -- tail", False),
    ("select coalesce(phone,'') from t", False),
    ("select count(*) from t", True),
]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && PYTEST_NO_APP=1 .venv/Scripts/python.exe -m pytest tests/test_query_policy_bypass.py -q`
Expected: FAIL

- [ ] **Step 3: 只补实现缺口**

若某条用例失败，回到 `compiler.py` / `star.py` 修，不在测试里放宽预期。
（`count(*)` 必须允许；其余含敏感列的星号/敏感列引用必须拒绝。）

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && PYTEST_NO_APP=1 .venv/Scripts/python.exe -m pytest tests/test_query_policy_bypass.py -q`
Expected: PASS（12 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/tests/test_query_policy_bypass.py
git commit -m "test(query): 12 条权限绕过回归用例"
```

---

### Task 12: 策略管理接口与权限

**Files:**
- Modify: `backend/app/plugin/module_ai/query/controller.py`（新增 4 个路由）
- Create: `backend/app/plugin/module_ai/query/policy_api.py`
- Test: `backend/tests/test_query_policy_api.py`

**Interfaces:**
- Produces:
  ```
  GET    /ai/query/policy/list?resource_kind=&resource_code=
  POST   /ai/query/policy/save
  POST   /ai/query/policy/delete        {"ids": [1,2]}
  GET    /ai/query/access/explain?user_id=&table=&column=
  GET    /ai/query/access/logs?limit=100
  ```

- [ ] **Step 1: 写失败测试**

```python
def test_policy_routes_registered():
    from main import create_app  # 或在 openapi 里断言
    paths = create_app().openapi()["paths"]
    assert "/api/v1/ai/query/policy/list" in paths
    assert "/api/v1/ai/query/access/explain" in paths
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_query_policy_api.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

路由权限：`module_ai:query:policy:query|create|update|delete`，在
`init_app._ensure_ai_menus()` 幂等补齐（沿用现有菜单注册函数）。explain 复用
`engine.decide_table/decide_column` + 审计表。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_query_policy_api.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/controller.py \
        backend/app/plugin/module_ai/query/policy_api.py \
        backend/tests/test_query_policy_api.py
git commit -m "feat(query): 策略管理接口 + 权限解释接口"
```

---

### Task 13: 端到端冒烟（真实链路）

**Files:**
- Create: `backend/scripts/query_policy_smoke.py`
- Modify: `AGENTS.md`（在「改问数时的提交前冒烟」一节追加一条）

- [ ] **Step 1: 写冒烟脚本**

覆盖：① 无主体 → deny；② 敏感表 `select *` → deny；③ 带行策略的表（临时建一条
`allow` + `condition`）→ 生成的 SQL 含过滤条件；④ 审计表有对应记录；⑤ 退出码非 0 即失败。

- [ ] **Step 2: 跑冒烟**

Run: `cd backend && .venv/Scripts/python.exe scripts/query_policy_smoke.py`
Expected: 5/5 通过，退出码 0

- [ ] **Step 3: 更新 AGENTS**

在「改问数（`module_ai/query`）时的提交前冒烟（强制）」里加一句：
`uv run python scripts/query_policy_smoke.py`（约 20s，验权限网关与星号止血）。

- [ ] **Step 4: 提交**

```bash
git add backend/scripts/query_policy_smoke.py AGENTS.md
git commit -m "test(query): 权限网关端到端冒烟 + 写入 AGENTS"
```

---

## Self-Review

**Spec coverage：** §3 概念（T2/T4）、§4 数据模型（T1）、§4.1 迁移（T8）、§5.1 流程（T6/T9）、
§5.2 行（T9）、§5.3 列（T9/T5）、§5.4 视图（T10）、§5.6 允许清单（T9/T11）、§6 上下文（计划 B）、
§7 网关（T6/T7）、§8 审计（T3/T12）、§9 派生（计划 C）、§10 灰度（T6）、§11 验收（T11/T13）。

**未纳入本计划（按 spec 拆到 B/C）：** 上下文裁剪（P3）、全入口 cron/导出（P4/P5）、多层视图（P5）。

**类型一致性：** `Principal` / `Decision` / `Policy` / `AccessPlan` 在 T2/T4/T9 定义，后续任务只引用；
`prepare(..., entry=...)` 在 T6 定义、T7 透传；`rewrite(sql, plan, dialect=...)` 在 T9 定义、T11 调用。

**Review Focus 对应测试：** ①T5/T11 ②T5/T11（解析失败）③T4（缺属性）④T10 ⑤T3（审计失败不抛）。

**比例：** 计划 13 个任务、约 500 行；spec 约 430 行。未写实现代码正文，只给签名、断言与关键规则。
