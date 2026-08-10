### Task 2: Alembic 迁移 — 建仓库表、加列、聚合回填数据

**Files:**
- Create: `backend/app/alembic/versions/<new_rev>_model_repo_split.py`
- Modify: `backend/app/alembic/versions/c9f2a1b4d8e3_*.py`（若需要调整依赖）
- Test: `backend/tests/test_migration_model_repo.py`（新建）

**Interfaces:**
- Consumes: 现有 `train_models` 表数据（41 条，含 `vv1` 版本污染）
- Produces: `train_model_repos` 表 + `train_models.repo_id` 回填 + 版本号规范化

- [ ] **Step 1: 生成迁移骨架**

Run: `cd backend && uv run main.py revision --env=dev -m "model repo split"`
Expected: 生成 `backend/app/alembic/versions/<hash>_model_repo_split.py`

- [ ] **Step 2: 写迁移逻辑（upgrade + downgrade）**

编辑生成的迁移文件，替换 upgrade/downgrade 主体：

```python
"""模型仓库/版本拆分迁移

Revision ID: <hash>
Revises: <previous_rev>
Create Date: 2026-08-02

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "<hash>"
down_revision = "<previous_rev>"
branch_labels = None
depends_on = None


def _normalize_version(raw: str) -> str:
    """'vv1' / 'v1' / '1' -> 'v1'"""
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    n = int(digits) if digits else 1
    return f"v{n}"


def upgrade() -> None:
    # 复用现有 PG 枚举类型 trainframework（train_models.framework 已用它，避免重复 CREATE TYPE）
    op.create_table(
        "train_model_repos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("uuid", sa.String(36), nullable=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("framework", sa.Enum(name="trainframework"), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("latest_version_id", sa.Integer(), nullable=True),
        sa.Column("annotation_dataset_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), server_default="draft", nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_id", sa.Integer(), nullable=True),
        sa.Column("updated_id", sa.Integer(), nullable=True),
        sa.Column("deleted_id", sa.Integer(), nullable=True),
        sa.Column("created_time", sa.DateTime(), nullable=True),
        sa.Column("updated_time", sa.DateTime(), nullable=True),
        sa.Column("deleted_time", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("name"),
    )
    op.add_column("train_models", sa.Column("repo_id", sa.Integer(), nullable=True))

    # 聚合回填：按 name 建仓库，版本号规范化
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, name, version, framework FROM train_models WHERE is_deleted = false")
    ).fetchall()
    repos: dict[str, int] = {}
    for row in rows:
        rid, name, version, framework = row
        if name not in repos:
            result = conn.execute(
                sa.text(
                    "INSERT INTO train_model_repos (name, framework, status, created_time, updated_time) "
                    "VALUES (:name, :framework, 'draft', NOW(), NOW()) RETURNING id"
                ),
                {"name": name, "framework": framework},
            )
            repo_id = result.scalar()
            repos[name] = repo_id
        else:
            repo_id = repos[name]
        norm_ver = _normalize_version(version)
        conn.execute(
            sa.text("UPDATE train_models SET repo_id = :rid, version = :ver WHERE id = :id"),
            {"rid": repo_id, "ver": norm_ver, "id": rid},
        )

    # 回填 latest_version_id：每个仓库取 created_time 最新版本
    repo_rows = conn.execute(
        sa.text(
            "SELECT r.id, v.id AS vid FROM train_model_repos r "
            "JOIN LATERAL ("
            "  SELECT id FROM train_models v "
            "  WHERE v.repo_id = r.id AND v.is_deleted = false "
            "  ORDER BY v.created_time DESC NULLS LAST, v.id DESC LIMIT 1"
            ") v ON true"
        )
    ).fetchall()
    for repo_id, vid in repo_rows:
        conn.execute(
            sa.text("UPDATE train_model_repos SET latest_version_id = :vid WHERE id = :rid"),
            {"vid": vid, "rid": repo_id},
        )


def downgrade() -> None:
    op.drop_column("train_models", "repo_id")
    op.drop_table("train_model_repos")
```

- [ ] **Step 3: 写迁移测试（针对 `_normalize_version` 纯函数）**

`backend/tests/test_migration_model_repo.py`:

```python
"""迁移工具函数测试。"""
from app.alembic.versions import __path__  # noqa: F401  (确保包可导入)


def test_normalize_version_variants():
    from importlib import import_module
    import os
    from pathlib import Path

    # 动态导入生成的迁移模块
    versions_dir = Path(__file__).parent.parent / "app" / "alembic" / "versions"
    mod_file = [p for p in versions_dir.glob("*_model_repo_split.py")][0]
    mod = import_module(f"app.alembic.versions.{mod_file.stem}")
    assert mod._normalize_version("v1") == "v1"
    assert mod._normalize_version("vv1") == "v1"
    assert mod._normalize_version("1") == "v1"
    assert mod._normalize_version(None) == "v1"
    assert mod._normalize_version("") == "v1"
```

- [ ] **Step 4: 运行迁移测试**

Run: `cd backend && uv run pytest tests/test_migration_model_repo.py -v`
Expected: PASS（`_normalize_version` 五组断言全过）

- [ ] **Step 5: 在真实库执行迁移（dev 环境）**

Run: `cd backend && uv run main.py upgrade --env=dev`
Expected: 输出包含 `Running upgrade ... -> <hash>`；验证：

```bash
uv run python -c "
import asyncio
from sqlalchemy import text
from app.core.database import async_db_session
async def main():
    async with async_db_session() as db:
        repos = (await db.execute(text('SELECT COUNT(*) FROM train_model_repos'))).scalar()
        orphan = (await db.execute(text('SELECT COUNT(*) FROM train_models WHERE repo_id IS NULL'))).scalar()
        vv = (await db.execute(text(\"SELECT COUNT(*) FROM train_models WHERE version LIKE 'v%v%'\"))).scalar()
        print(f'repos={repos} orphan={orphan} double_v={vv}')
asyncio.run(main())
"
```

Expected: `repos=<~30> orphan=0 double_v=0`

- [ ] **Step 6: 提交**

```bash
git add backend/app/alembic/versions/*_model_repo_split.py backend/tests/test_migration_model_repo.py
git commit -m "feat(train): split train_models into repo+version tables with data backfill"
```

---


