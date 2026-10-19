"""评测：数据集/条目 CRUD 与运行（逐条走统一检索管线后计算指标）。"""
from __future__ import annotations

from sqlalchemy import select

from app.core.database import async_db_session

from ..model import AiEvalItemModel, AiEvalRunModel, AiEvalSetModel
from .metrics import evaluate_items


def _set_to_dict(row: AiEvalSetModel) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description or "",
        "kb_ids": row.kb_ids or [],
        "created_time": row.created_time,
    }


def _item_to_dict(row: AiEvalItemModel) -> dict:
    return {
        "id": row.id,
        "set_id": row.set_id,
        "query": row.query,
        "expected_chunk_ids": row.expected_chunk_ids or [],
        "expected_files": row.expected_files or [],
        "note": row.note,
    }


async def create_set(name: str, kb_ids: list[int], description: str | None = None, auth=None) -> dict:
    async with async_db_session.begin() as db:
        row = AiEvalSetModel(name=name, kb_ids=list(kb_ids or []), description=description or "")
        if auth is not None:
            row.created_id = getattr(getattr(auth, "user", None), "id", None)
        db.add(row)
        await db.flush()
        await db.refresh(row)
        return _set_to_dict(row)


async def list_sets() -> list[dict]:
    async with async_db_session() as db:
        rows = (
            (
                await db.execute(
                    select(AiEvalSetModel)
                    .where(AiEvalSetModel.is_deleted.is_(False))
                    .order_by(AiEvalSetModel.id.desc())
                )
            )
            .scalars()
            .all()
        )
    return [_set_to_dict(row) for row in rows]


async def add_item(
    set_id: int,
    query: str,
    *,
    expected_chunk_ids: list[int] | None = None,
    expected_files: list[str] | None = None,
    note: str | None = None,
) -> dict:
    async with async_db_session.begin() as db:
        eval_set = await db.get(AiEvalSetModel, set_id)
        if not eval_set or eval_set.is_deleted:
            raise ValueError("评测集不存在")
        row = AiEvalItemModel(
            set_id=set_id,
            query=query,
            expected_chunk_ids=list(expected_chunk_ids or []),
            expected_files=list(expected_files or []),
            note=note,
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)
        return _item_to_dict(row)


async def list_items(set_id: int) -> list[dict]:
    async with async_db_session() as db:
        rows = (
            (
                await db.execute(
                    select(AiEvalItemModel)
                    .where(
                        AiEvalItemModel.set_id == set_id,
                        AiEvalItemModel.is_deleted.is_(False),
                    )
                    .order_by(AiEvalItemModel.id.asc())
                )
            )
            .scalars()
            .all()
        )
    return [_item_to_dict(row) for row in rows]


async def run_eval(
    set_id: int,
    kb_id: int,
    config: dict | None = None,
    *,
    auth=None,
    progress_cb=None,
) -> dict:
    """对评测集逐条检索并计算指标（同步实现，供 worker 调用）。"""
    from ..service import AiKnowledgeService

    cfg = dict(config or {})
    top_k = int(cfg.get("top_k") or 5)
    items = await list_items(set_id)
    if not items:
        raise ValueError("评测集没有条目")

    async with async_db_session.begin() as db:
        run = AiEvalRunModel(
            set_id=set_id,
            kb_id=kb_id,
            config=cfg,
            metrics=None,
            status="running",
        )
        if auth is not None:
            run.created_id = getattr(getattr(auth, "user", None), "id", None)
        db.add(run)
        await db.flush()
        run_id = run.id

    samples: list[dict] = []
    try:
        for index, item in enumerate(items, start=1):
            rows = await AiKnowledgeService.search(
                [kb_id],
                item["query"],
                top_k,
                use_rerank=bool(cfg.get("use_rerank", True)),
                min_score=float(cfg.get("min_score") or 0.0),
                use_weighted=bool(cfg.get("use_weighted", False)),
                filters=cfg.get("filters"),
                mode=str(cfg.get("mode") or "hybrid"),
            )
            samples.append(
                {
                    "retrieved": [row["chunk_id"] for row in rows],
                    "expected": item.get("expected_chunk_ids") or [],
                }
            )
            if progress_cb is not None:
                await progress_cb(index, len(items))
        metrics = evaluate_items(samples, k=top_k)
        async with async_db_session.begin() as db:
            run = await db.get(AiEvalRunModel, run_id)
            if run:
                run.metrics = metrics
                run.status = "succeeded"
        return {"run_id": run_id, **metrics}
    except Exception as e:  # noqa: BLE001
        async with async_db_session.begin() as db:
            run = await db.get(AiEvalRunModel, run_id)
            if run:
                run.status = "failed"
                run.error = str(e)[:2000]
        raise


async def list_runs(kb_id: int, limit: int = 50) -> list[dict]:
    async with async_db_session() as db:
        rows = (
            (
                await db.execute(
                    select(AiEvalRunModel)
                    .where(
                        AiEvalRunModel.kb_id == kb_id,
                        AiEvalRunModel.is_deleted.is_(False),
                    )
                    .order_by(AiEvalRunModel.id.desc())
                    .limit(max(1, int(limit)))
                )
            )
            .scalars()
            .all()
        )
    return [
        {
            "id": row.id,
            "set_id": row.set_id,
            "kb_id": row.kb_id,
            "config": row.config or {},
            "metrics": row.metrics or {},
            "status": row.status,
            "error": row.error,
            "created_time": row.created_time,
        }
        for row in rows
    ]
