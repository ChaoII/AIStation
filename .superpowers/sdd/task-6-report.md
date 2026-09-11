# Task 6 Report: 训练模块迁移补列与启动自检

## Status: DONE_WITH_CONCERNS

## Implemented

1. **新增补列清单模块** `backend/app/plugin/module_train/schema_check.py`
   - `MISSING_TRAIN_COLUMNS: dict[str, list[tuple[str, str]]]`：覆盖 `train_tasks`(6列)、`train_models`(2列)、`train_evals`(10列)。
   - `async ensure_train_columns(engine)`：逐列 `ALTER TABLE <t> ADD COLUMN IF NOT EXISTS <c> <type>`，`engine.begin()` 单事务、逐条 try/except。
2. **新增幂等 Alembic 迁移** `backend/app/alembic/versions/7a1b2c3d4e5f_train_missing_columns.py`
   - `revision = "7a1b2c3d4e5f"`，`down_revision = "1c2d3e4f5a6b"`。
   - `upgrade()` 遍历同一份 `_ADDITIONS` 清单，执行 `ADD COLUMN IF NOT EXISTS`；`downgrade()` 为 no-op（增量列不回退）。
3. **接入启动补列** `backend/app/scripts/init_app.py` `lifespan`
   - 用 `await ensure_train_columns(async_engine)` 替换原先 `for col in ["metrics_log","best_metrics","last_metrics"]` 与 `train_evals` 的 ad-hoc `ALTER` 循环。
   - 保留 `CREATE TABLE IF NOT EXISTS train_predicts` 整段不变。
4. **新增测试** `backend/tests/test_train_schema_check.py`（brief 提供，3 个用例）。
   - 断言清单非空、预期列在清单中、清单所有列均为对应 ORM 模型真实字段。

## Tests & Results

- `uv run pytest tests/test_train_schema_check.py -q` → **3 passed**
- `uv run pytest -q`（全量）→ **77 passed, 1 warning**（warning 为 fastapi_limiter 既有 DeprecationWarning）
- `uv run ruff check <4 个任务文件>` → **All checks passed!**
- `uv run alembic heads` → **`7a1b2c3d4e5f (head)`**，单一 head，迁移链正确。
- 全仓 `uv run ruff check` → 277 个既存错误，任务文件 0 新增。

## TDD Evidence (RED / GREEN)

- **RED**：先写 `tests/test_train_schema_check.py`，运行报
  `ImportError: cannot import name 'schema_check' from 'app.plugin.module_train'`（collection 阶段失败，符合"模块不存在"预期）。
- **GREEN**：创建 `schema_check.py` 后重跑 → `3 passed`。
- 全量保持在 GREEN：`77 passed`。

## Files Changed

- 新增 `backend/app/plugin/module_train/schema_check.py`
- 新增 `backend/app/alembic/versions/7a1b2c3d4e5f_train_missing_columns.py`
- 修改 `backend/app/scripts/init_app.py`
- 新增 `backend/tests/test_train_schema_check.py`

## Self-Review

- [x] `MISSING_TRAIN_COLUMNS` 中所有列均在 ORM 模型上真实存在（`test_models_have_declared_columns` 通过）。
- [x] 迁移幂等：全部使用 `ADD COLUMN IF NOT EXISTS`。
- [x] 启动仍创建 `train_predicts`（diff 确认该段未改动）。
- [x] 无重复/残留 `ALTER` 语句：旧的 3 列 + 5 列循环已删除，改由 `ensure_train_columns` 统一覆盖（且新清单是旧清单的超集）。
- [x] 仅暂存 4 个任务文件，未 `git add -A`。
- [x] 全仓 ruff 自动修复了无关文件 `tests/test_paddlex_removal.py` → 已 `git checkout --` 还原。

## Fix

**问题**：`ensure_train_columns` 原实现把所有 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` 放在单个 `engine.begin()` 事务里，并用 `except Exception: pass` 吞异常。PostgreSQL 下第一条失败即中止事务，后续语句全部抛 `InFailedSqlTransactionError`（同样被吞），commit 回滚 → 整个补列静默失效，违背"根因优先、不靠 try/except 掩盖"原则。

**修复**（仅改 `backend/app/plugin/module_train/schema_check.py`）：
1. 每条 DDL 使用独立 `async with engine.begin() as conn:`，单列失败不再牵连/回滚其他列。
2. 失败改为 `log.warning(f"train backfill skipped {table}.{name}: {e}")`（`from app.core.logger import log`），不再静默吞掉，且不 re-raise（补列仍为 best-effort）。
3. `MISSING_TRAIN_COLUMNS` 与函数签名 `async def ensure_train_columns(engine) -> None` 不变；未改 Alembic 迁移与 `init_app.py`。

**覆盖测试**：`backend/tests/test_train_schema_check.py`（3 用例：清单非空且列名有效、预期列在清单中、清单列均为对应 ORM 真实字段）。

**验证命令与结果**：
- `uv run pytest tests/test_train_schema_check.py -q` → `3 passed in 0.02s`
- `uv run pytest -q`（全量）→ `77 passed, 1 warning in 29.63s`（warning 为 fastapi_limiter 既有 DeprecationWarning）
- `uv run ruff check app/plugin/module_train/schema_check.py` → `All checks passed!`

**提交**：`fix(train): 补列逐条独立事务并记录失败`

## Concerns

1. **interface 未实现 `missing_columns_for_model`**：brief 的 Interfaces 段落声明了 `missing_columns_for_model(model) -> set[str]`，但 Step 3 给定的代码与测试均未包含/使用它。按"exact code verbatim / 只做要求项"原则未自行新增，以免引入未测试代码。若后续任务依赖该函数需补。
2. **`ensure_train_columns` 单事务 + 逐条 except**：PostgreSQL 中一条语句失败会使整个事务进入 aborted 状态，后续 `execute` 会持续抛 `InFailedSqlTransaction` 并被吞掉，导致失败点之后的列静默不再补齐。当前只针对已存在的三张表执行 `ADD COLUMN IF NOT EXISTS`，触发概率低，但属于潜在风险。这是 brief 指定实现，未改。
3. **`train_evals.framework` 类型为 `VARCHAR(16)`**，而 ORM 声明为 `SAEnum(TrainFramework)`；新库由 SQLAlchemy 建 enum，旧库缺失时补成 VARCHAR。brief 风险节已将其列为"预期"（同名列类型不同时 `IF NOT EXISTS` 跳过）。
4. **偏离 brief 之处**（均已说明）：
   - 迁移文件删除了 brief 模板里的 `import sqlalchemy as sa`（未使用，会产生新 F401）。
   - 测试用例 `for table, columns` 改名为 `for _table, columns`（brief 原样会触发新 B007）。
   - 未添加 brief Step 5 的 `from app.api.v1.module_annotation.dataset.model import DatasetModel`——`ensure_train_columns` 使用纯 SQL，无需 ORM 元数据注册，该导入在当前上下文中无作用。
