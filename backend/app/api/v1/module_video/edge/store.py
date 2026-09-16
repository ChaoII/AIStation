"""边缘事件持久化：只落有检测的事件，``event_id`` 幂等。

写入策略：
- ``objects`` 与 ``detections`` 皆空（静默期心跳）→ 不落库，返回 ``None``；
- ``event_id`` 缺失 → 无法幂等，返回 ``None``；
- PostgreSQL 用 ``ON CONFLICT DO NOTHING``（真幂等、并发安全）；
  其它数据库降级为「先查后插 + 唯一键兜底」；
- 内联 ``snapshot_data``（base64）一律丢弃，只保留 ``snapshot_ref``；
- 失败仅告警并返回 ``None``，绝不向上抛异常（不阻断告警链路）。
"""
import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.module_video.edge.model import EdgeEventModel
from app.api.v1.module_video.inference.temporal import to_epoch
from app.config.setting import settings

log = logging.getLogger(__name__)


def count_events(session: Session) -> int:
    """统计边缘事件总数（同步会话；测试/运维辅助）。"""
    return int(session.execute(select(func.count()).select_from(EdgeEventModel)).scalar() or 0)


def get_event_by_event_id(session: Session, event_id: str) -> EdgeEventModel | None:
    """按 ``event_id`` 读取事件行（同步会话；测试/运维辅助）。"""
    return session.execute(
        select(EdgeEventModel).where(EdgeEventModel.event_id == event_id)
    ).scalars().first()


def _event_datetime(event: dict) -> datetime:
    """事件时间：与告警链路一致用 ``to_epoch`` 归一化，非法/缺失安全回退当前时间。"""
    raw = event.get("frame_timestamp")
    if raw is None:
        raw = event.get("ts")
    try:
        return datetime.fromtimestamp(to_epoch(raw), tz=UTC)
    except (OverflowError, OSError, ValueError, TypeError):
        return datetime.now(UTC)


def _build_values(event: dict, *, matched: bool, rule_id, matched_leaves) -> dict:
    """构造入库字段；``snapshot_data`` 不在此列，天然丢弃。"""
    objects = event.get("objects")
    detections = event.get("detections")
    snapshot_ref = event.get("snapshot_ref") or event.get("snapshot_path")
    return {
        "event_id": str(event.get("event_id")),
        "edge_code": event.get("edge_code"),
        "camera_id": event.get("camera_id"),
        "task_id": event.get("task_id"),
        "algorithm_type": event.get("algorithm_type"),
        "ts": _event_datetime(event),
        "objects": objects if isinstance(objects, list) else None,
        "detections": detections if isinstance(detections, list) else None,
        "latency_ms": event.get("latency_ms"),
        "snapshot_ref": str(snapshot_ref) if snapshot_ref else None,
        "matched": bool(matched),
        "matched_rule_id": rule_id,
        "matched_leaves": matched_leaves or [],
    }


async def record_edge_event(
    event: dict, *, matched: bool, rule_id, matched_leaves
) -> int | None:
    """落库一条边缘事件；重复 ``event_id`` / 空事件返回 ``None``，失败仅告警。"""
    if not isinstance(event, dict) or not event.get("event_id"):
        return None
    # 只落有检测的事件：objects 与 detections 皆空的静默期心跳不落库
    if not (event.get("objects") or event.get("detections")):
        return None

    values = _build_values(
        event, matched=matched, rule_id=rule_id, matched_leaves=matched_leaves
    )
    try:
        # 延迟导入：便于测试 monkeypatch app.core.database.async_db_session
        from app.core.database import async_db_session

        if settings.DATABASE_TYPE == "postgres":
            # PG：冲突即忽略，返回 None 表示重复
            stmt = (
                pg_insert(EdgeEventModel)
                .values(**values)
                .on_conflict_do_nothing(index_elements=["event_id"])
                .returning(EdgeEventModel.id)
            )
            async with async_db_session.begin() as session:
                return (await session.execute(stmt)).scalar_one_or_none()

        # 其它数据库降级：先查后插，唯一键冲突兜底（并发场景）
        async with async_db_session.begin() as session:
            exists = await session.scalar(
                select(EdgeEventModel.id).where(EdgeEventModel.event_id == values["event_id"])
            )
            if exists is not None:
                return None
            obj = EdgeEventModel(**values)
            try:
                # 保存点隔离：并发冲突只回滚本次插入
                async with session.begin_nested():
                    session.add(obj)
                    await session.flush()
            except IntegrityError:
                return None
            return obj.id
    except Exception as e:
        log.warning(f"边缘事件落库失败: {e}")
        return None
