# 数据库迁移与部署 Runbook（Alembic）

适用：`backend/`（FastAPI + SQLAlchemy 2.0 + Alembic）。命令均在后端目录执行。

## 1. 支持矩阵

| 数据库 | `alembic upgrade head`（空库重放） | `create_all` 建库 | 说明 |
|--------|-----------------------------------|-------------------|------|
| PostgreSQL | ✅ 完整支持（唯一生产路径） | ✅ | 原生方言；迁移链 20 个版本可从 base 一跑到底 |
| SQLite | ✅ 支持（经跨方言兼容层降级） | ✅ | `JSONB→JSON`、`DO`/`ALTER TYPE` 跳过、`ALTER`/外键走 batch 重建表 |
| MySQL | ⚠️ 尽力而为（未在本机实测，无 MySQL 服务） | ✅ | 类型降级已覆盖；`ADD COLUMN IF NOT EXISTS`/`CHECK ... NOT VALID` 已按方言分支，仍需在目标版本验证 |

跨方言实现见 `backend/app/alembic/dialect_compat.py`：`JSONB` 在 SQLite/MySQL 渲染为 `JSON`；
迁移脚本通过 `is_postgres()` / `is_sqlite()` 对 PG 专属语法显式分支。PG 语义保持不变
（已在临时 PG 库验证 `upgrade head` + 模型/库 schema 比对 `EMPTY_DIFF`）。

## 2. 常规部署流程

```bash
cd backend
# 1) 空库/新库：直接迁移
ENVIRONMENT=prod uv run alembic upgrade head      # 或 uv run main.py upgrade --env=prod
# 2) 启动应用
uv run main.py run --env=prod
```

> Windows PowerShell：`$env:ENVIRONMENT="prod"; uv run alembic upgrade head`。
> 未设置 `ENVIRONMENT` 时 `setting.py` 会回退到类默认（mysql/localhost），务必显式指定。

## 3. 既有 `create_all` 库（无 `alembic_version`）

历史部署可能只跑过应用（`create_all` 建表），库里没有 `alembic_version`。
此时直接 `upgrade head` 会从 base 迁移重放 `create_table` 并抛 `DuplicateTable`。

**启动时会自动处理**（`app/scripts/schema_stamp.py`，在 `init_app.lifespan` 中最先执行）：

| 检测到的状态 | 行为 |
|--------------|------|
| `no_tables`（空库） | 不写戳，交由 `create_all`/迁移创建 |
| `stamped`（已有版本记录） | 不干预 |
| `schema_matches_head`（表在、无记录、结构与当前模型一致 = 当前版本 `create_all` 建库） | **补写 `head`**，之后 `upgrade head` 成为安全空操作 |
| `legacy_mismatch`（表在、无记录、缺表或缺列） | **拒绝写戳**，日志打印缺失项与操作指引 |

`legacy_mismatch` 的处理步骤：

```bash
# 1) 备份数据库
# 2) 生成补齐脚本（对照当前模型）后人工审阅
uv run main.py revision --env=prod
# 3) 应用补齐脚本，或按缺失项手工 ADD COLUMN
uv run main.py upgrade --env=prod        # 若已打戳；否则待 schema 对齐后由启动自动打戳
# 4) 重新启动应用，确认日志出现「已为 create_all 库补写 Alembic 版本戳」
```

> 切勿对落后 schema 直接 `alembic stamp head`——会跳过缺失迁移。

手动补戳（确认 schema 与当前模型一致时）：

```bash
uv run alembic stamp head
```

## 4. 校验

```bash
# 迁移历史 / head
uv run alembic history
uv run alembic heads          # 必须只有 1 个 head
# 当前库版本
uv run alembic current
```

回归测试：

```bash
uv run pytest tests/test_alembic_dialect_compat.py tests/test_schema_stamp.py -q
# test_alembic_dialect_compat 含真实 SQLite 子进程 `upgrade head` 重放
```

## 5. 变更迁移的约定

- 新增/补列一律幂等：PG 用 `ADD COLUMN IF NOT EXISTS`，SQLite/MySQL 用
  `dialect_compat.portable_add_column`（先探测列）。
- 涉及 `ALTER COLUMN`/`ADD CONSTRAINT`：非 PG 走 `op.batch_alter_table`。
- 原始 SQL 中的 `JSONB`/`SERIAL`/`NOW()`/`TIMESTAMP WITHOUT TIME ZONE` 需按方言分支或经
  `a3f3956bb77b` 中的 `_exec_portable` 处理。
- 新增模型列必须同步登记 `app/scripts/init_app.py::ENSURE_NEW_COLUMNS`（兜底补列清单）。
