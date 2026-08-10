# Task 1 Report — 数据模型：新增仓库表 + 版本表加 repo_id

## Status: DONE

## What I implemented

- **`backend/app/plugin/module_train/model.py`**:
  - Added `TrainModelRepo(ModelMixin, UserMixin)` class **before** `TrainModel`, with `__tablename__ = "train_model_repos"` and columns: `name` (String(128), unique), `framework` (SAEnum(TrainFramework)), `description` (Text, nullable), `latest_version_id` (Integer, nullable), `annotation_dataset_id` (Integer, nullable), `status` (String(16), default="draft").
  - Added `repo_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="所属仓库ID")` as the **first** column in the `TrainModel` class body. All other `TrainModel` columns left unchanged.
  - No new imports needed — reused existing imports (`ModelMixin`, `UserMixin`, `Mapped`, `mapped_column`, `DateTime`, `Integer`, `String`, `Text`, `SAEnum`, `JSONB`).

- **`backend/tests/test_train_model_schema.py`** (new): two synchronous tests asserting `TrainModelRepo.__tablename__ == "train_model_repos"` + `name` column exists, and `repo_id` column exists on `TrainModel`. Mirrors the brief's test code verbatim.

## What I tested and results (TDD)

**RED** — `uv run pytest tests/test_train_model_schema.py -v` (before implementation):
```
ImportError: cannot import name 'TrainModelRepo' from 'app.plugin.module_train.model'
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
```

**GREEN** — after implementing model changes:
```
tests/test_train_model_schema.py::test_train_model_repo_table_declared PASSED [ 50%]
tests/test_train_model_schema.py::test_train_model_has_repo_id_column PASSED [100%]
============================== 2 passed in 0.01s ==============================
```

**Ruff** — `uv run ruff check app/plugin/module_train/model.py tests/test_train_model_schema.py`:
```
All checks passed!
```

**Regression check** — `uv run pytest tests/test_type_conversion.py` passed (4 passed). `test_main.py::test_check_readiness` / `test_check_health` fail with `concurrent.futures._base.CancelledError` — verified this is **pre-existing** by running the same tests on baseline commit `249755f` (via temp worktree) and reproducing identical errors. The `conftest.py` docstring documents this exact known limitation (repeated TestClient lifecycle driving one app). Unrelated to this change.

## Files changed

- `backend/app/plugin/module_train/model.py` (+12 lines: TrainModelRepo class + repo_id column)
- `backend/tests/test_train_model_schema.py` (new, 11 lines)

Commit `57f9b6b` contains only these two files. The `.superpowers/sdd/*.md` plan files were intentionally not staged.

## Self-review findings

- `TrainModelRepo` is correctly inserted **before** `TrainModel` in model.py, and `repo_id` is the first column of `TrainModel` — both match the brief.
- Column definitions match the brief verbatim (types, nullability, defaults, comments).
- No unused imports added; ruff clean.
- The class insertion preserves `TrainTask`, `TrainEval`, `TrainPredict`, `TrainDeploy` unchanged below.
- Note: model inherits `ModelMixin, UserMixin` per brief (no `TenantMixin`) — consistent with existing train models.

## Issues / concerns

- None blocking. `test_main.py` failures are pre-existing infrastructure quirks, not introduced here.
