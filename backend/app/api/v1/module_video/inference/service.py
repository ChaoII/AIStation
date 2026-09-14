import base64
import logging
import re
from datetime import datetime
from pathlib import Path

from app.config.setting import settings

log = logging.getLogger(__name__)


def pick_alarm_rule(rules: list, algorithm_type: str):
    """从多条候选规则中选一条：优先 alarm_type 精确匹配，否则第一条；空返回 None。"""
    if not rules:
        return None
    for r in rules:
        if getattr(r, "alarm_type", None) == algorithm_type:
            return r
    return rules[0]


def _as_float(raw) -> float | None:
    """尽力转换为 float；None/缺失/非数值返回 None。"""
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _bbox_center(d: dict) -> tuple[float, float] | None:
    """取检测框中心点 (x + w/2, y + h/2)；bbox 缺失/非法返回 None。"""
    if not isinstance(d, dict):
        return None
    bbox = d.get("bbox")
    if not isinstance(bbox, dict):
        return None
    x = _as_float(bbox.get("x"))
    y = _as_float(bbox.get("y"))
    w = _as_float(bbox.get("width"))
    h = _as_float(bbox.get("height"))
    if None in (x, y, w, h):
        return None
    return (x + w / 2.0, y + h / 2.0)


def _region_of(leaf: dict) -> list[tuple[float, float]] | None:
    """解析归一化多边形区域。

    缺失/None 返回 None（表示不限定区域）；非法（非多边形 / 坐标非数值）返回空列表，
    由调用方判为不命中。
    """
    if not isinstance(leaf, dict):
        return []
    region = leaf.get("region")
    if region is None:
        return None
    if not isinstance(region, (list, tuple)) or len(region) < 3:
        return []
    pts: list[tuple[float, float]] = []
    for p in region:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            return []
        x = _as_float(p[0])
        y = _as_float(p[1])
        if x is None or y is None:
            return []
        pts.append((x, y))
    return pts


def _point_on_segment(px, py, x1, y1, x2, y2, eps: float = 1e-9) -> bool:
    """判断点是否落在线段上（含端点），用于边界确定性判定。"""
    cross = (px - x1) * (y2 - y1) - (py - y1) * (x2 - x1)
    if abs(cross) > eps:
        return False
    dot = (px - x1) * (px - x2) + (py - y1) * (py - y2)
    return dot <= eps


def _point_in_polygon(x: float, y: float, pts: list[tuple[float, float]]) -> bool:
    """射线法判断点是否在多边形内；落在边界（含端点）视为命中。"""
    if not pts or len(pts) < 3:
        return False
    n = len(pts)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if _point_on_segment(x, y, xi, yi, xj, yj):
            return True
        if (yi > y) != (yj > y):
            x_cross = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_cross:
                inside = not inside
        j = i
    return inside


def _matches_label(d: dict, leaf: dict) -> bool:
    """label/labels 过滤：labels 非空优先；都缺省表示任意目标。"""
    if not isinstance(d, dict) or not isinstance(leaf, dict):
        return False
    labels = leaf.get("labels")
    if isinstance(labels, (list, tuple)) and labels:
        return d.get("label") in labels
    label = leaf.get("label")
    if label is None:
        return True
    return d.get("label") == label


def _in_region(d: dict, leaf: dict) -> bool:
    """检测框中心是否落在区域多边形内；未限定区域返回 True，非法区域返回 False。"""
    if not isinstance(leaf, dict) or leaf.get("region") is None:
        return True
    pts = _region_of(leaf)
    if not pts:  # 非法区域
        return False
    center = _bbox_center(d)
    if center is None:
        return False
    return _point_in_polygon(center[0], center[1], pts)


def _match_conditions(conditions: dict | None, detections: list[dict]) -> bool:
    """评估规则条件树；空/None 视为命中。

    叶子支持 attribute：{"subject":"attribute","field":名,"op":"lt|gt|le|ge|eq","value":数}。
    事件里 attributes 为 {属性名: 分数}（分数=具有该属性的概率）；违规=分数低于阈值。
    OCR 文本叶子：
    - text_match：{"subject":"text_match","regex":"..."}，任一 detection.text 命中正则即命中；
      非法正则视为不命中。
    - ocr_label：{"subject":"ocr_label","contains":"..."}，任一 detection.text 包含子串即命中。
    对象/区域/计数叶子（基于 bbox 中心与归一化多边形区域）：
    - object_present：{"subject":"object_present","label"?,"labels"?,"region"?,"min_confidence"?}
      存在满足 label/labels、位于 region 内、且置信度 >= min_confidence 的目标即命中。
    - zone_enter：{"subject":"zone_enter","label","region"}，目标中心落入区域即命中；
      未限定 region 时等价于 object_present（不限置信度）。
    - count：{"subject":"count","label"?,"region"?,"op":">=|>|<=|<|==","value":n}，
      统计满足条件的目标数并与 value 比较。
    其它叶子后续扩展；未知叶子不命中。
    本函数对异常输入（JSON null / 非数值 / 非 dict）一律按不命中处理，绝不向上抛异常，
    避免单条脏规则导致整个告警事件被丢弃。
    """
    if not conditions:
        return True
    if not isinstance(conditions, dict):
        # 非 dict 的脏条件不得抛异常，按不命中处理
        return False

    # 过滤脏检测项（非 dict 一律跳过），后续统一使用该列表
    raw_dets = detections if isinstance(detections, (list, tuple)) else []
    dets = [d for d in raw_dets if isinstance(d, dict)]

    def _to_float(raw) -> float | None:
        """尽力转换为 float；null/缺失/非数值返回 None，由调用方跳过该叶子。"""
        if raw is None:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    def _texts() -> list[str]:
        """收集所有 detection 上的 OCR 文本（非字符串一律跳过）。"""
        return [d["text"] for d in dets if isinstance(d.get("text"), str)]

    def eval_leaf(leaf: dict) -> bool:
        subject = leaf.get("subject")
        if subject == "attribute":
            field = leaf.get("field")
            op = leaf.get("op", "eq")
            value = _to_float(leaf.get("value"))
            if value is None:
                return False
            for d in dets:
                score = (d.get("attributes") or {}).get(field)
                score = _to_float(score)
                if score is None:
                    continue
                if op == "lt" and score < value:
                    return True
                if op == "gt" and score > value:
                    return True
                if op == "le" and score <= value:
                    return True
                if op == "ge" and score >= value:
                    return True
                if op == "eq" and score == value:
                    return True
            return False
        if subject == "text_match":
            pattern = leaf.get("regex")
            if not isinstance(pattern, str):
                return False
            try:
                compiled = re.compile(pattern)
            except re.error:
                # 非法正则视为不命中，避免单条脏规则导致告警事件被丢弃
                return False
            return any(compiled.search(text) for text in _texts())
        if subject == "ocr_label":
            needle = leaf.get("contains")
            if not isinstance(needle, str):
                return False
            return any(needle in text for text in _texts())
        if subject in ("object_present", "zone_enter"):
            min_conf = None
            if subject == "object_present":
                raw_min = leaf.get("min_confidence")
                if raw_min is not None:
                    min_conf = _as_float(raw_min)
                    if min_conf is None:
                        # min_confidence 非法（非数值）→ 不命中
                        return False
            for d in dets:
                if not _matches_label(d, leaf):
                    continue
                if not _in_region(d, leaf):
                    continue
                if min_conf is not None:
                    conf = _as_float(d.get("confidence"))
                    if conf is None or conf < min_conf:
                        continue
                return True
            return False
        if subject == "count":
            op = leaf.get("op")
            if op not in (">=", ">", "<=", "<", "=="):
                return False
            target = _as_float(leaf.get("value"))
            if target is None:
                return False
            matched = sum(1 for d in dets if _matches_label(d, leaf) and _in_region(d, leaf))
            if op == ">=":
                return matched >= target
            if op == ">":
                return matched > target
            if op == "<=":
                return matched <= target
            if op == "<":
                return matched < target
            return matched == target
        return False

    def eval_node(node: dict) -> bool:
        # 非 dict 节点（脏规则）不得抛异常，按不命中处理
        if not isinstance(node, dict):
            return False
        # 逻辑节点（and/or/not）与属性叶子都带 "op"，用逻辑算子集合区分：
        # 叶子 op 为 lt/gt/le/ge/eq 或比较符，若误当逻辑节点会直接不命中。
        op = node.get("op")
        if op in ("and", "or", "not"):
            kids = node.get("children") or []
            if op == "and":
                return all(eval_node(k) for k in kids) if kids else True
            if op == "or":
                return any(eval_node(k) for k in kids)
            return not any(eval_node(k) for k in kids)
        return eval_leaf(node)

    return eval_node(conditions)


class InferenceService:

    @classmethod
    async def process_detection_callback(cls, event: dict) -> dict:
        """Process a detection event from a worker callback."""
        from sqlalchemy import select

        from app.api.v1.module_video.alarm.model import AlarmRecordModel, AlarmRuleModel
        from app.core.database import async_db_session

        task_id = event.get("task_id")
        camera_id = event.get("camera_id")
        algorithm_type = event.get("algorithm_type")
        detections = event.get("detections", [])
        snapshot_data = event.get("snapshot_data")
        snapshot_path = event.get("snapshot_path")
        frame_timestamp = event.get("frame_timestamp")

        if not detections:
            return {"alarm_created": False, "reason": "no_detections"}

        # Save snapshot
        saved_snapshot_path = None
        if snapshot_data:
            try:
                detectors_dir = Path(settings.DETECTIONS_DIR)
                detectors_dir.mkdir(parents=True, exist_ok=True)
                snap_name = snapshot_path or f"{camera_id}_{int(datetime.now().timestamp())}.jpg"
                snap_full = detectors_dir / snap_name
                snap_full.parent.mkdir(parents=True, exist_ok=True)
                img_bytes = base64.b64decode(snapshot_data)
                snap_full.write_bytes(img_bytes)
                saved_snapshot_path = str(snap_full)
            except Exception as e:
                log.warning(f"保存快照失败: {e}")
        elif snapshot_path:
            # 边缘事件：快照已由 Agent 上传对象存储，此处仅存相对引用
            saved_snapshot_path = snapshot_path

        # Find matching alarm rule
        rule = None
        async with async_db_session() as session:
            stmt = select(AlarmRuleModel).where(
                AlarmRuleModel.camera_id == camera_id,
                AlarmRuleModel.alarm_type == (algorithm_type or "AI_DETECTION"),
                AlarmRuleModel.status.is_(True),
                AlarmRuleModel.is_deleted.is_(False),
            )
            result = await session.execute(stmt)
            rule = pick_alarm_rule(result.scalars().all(), algorithm_type or "AI_DETECTION")

        if rule is not None and rule.conditions and not _match_conditions(rule.conditions, detections):
            return {"alarm_created": False, "reason": "rule_not_matched"}

        severity = rule.severity if rule else "WARNING"

        alarm_data = {
            "camera_id": camera_id,
            "rule_id": rule.id if rule else None,
            "alarm_type": algorithm_type or "AI_DETECTION",
            "severity": severity,
            "snapshot_path": saved_snapshot_path,
            "ai_result": {
                "task_id": task_id,
                "algorithm_type": algorithm_type,
                "detections": detections,
                "frame_timestamp": frame_timestamp,
            },
            "description": f"AI 检测到 {len(detections)} 个目标: {', '.join(d.get('label', '') for d in detections[:5])}",
            "status": "PENDING",
        }

        # Create alarm record
        try:
            async with async_db_session.begin() as session:
                record = AlarmRecordModel(**alarm_data)
                session.add(record)
                await session.flush()
                alarm_id = record.id

            # 触发事件联动（ALARM 事件 → RECORD/通知等动作，逻辑闭环）
            try:
                from app.api.v1.module_video.event.service import EventService
                await EventService.execute_linkage_actions(camera_id, "ALARM")
            except Exception as e:
                log.warning(f"事件联动执行异常: {e}")

            # Async notification
            if rule:
                try:
                    # dispatch_notification 只读 auth.db；提供真实会话而非构造 AuthSchema(db=None)
                    from types import SimpleNamespace

                    from app.utils.notification import dispatch_notification
                    async with async_db_session() as notify_db:
                        auth_like = SimpleNamespace(db=notify_db)
                        alarm_dict = {
                            "id": alarm_id,
                            "camera_id": camera_id,
                            "alarm_type": algorithm_type,
                            "severity": severity,
                            "alarm_time": datetime.now().isoformat(),
                            "description": alarm_data["description"],
                            "snapshot_path": saved_snapshot_path,
                            "camera": {"name": ""},
                            "rule_id": rule.id,
                        }
                        rule_dict = {
                            "id": rule.id,
                            "name": rule.name,
                            "severity": rule.severity,
                            "notify_channels": rule.notify_channels,
                        }
                        await dispatch_notification(auth_like, alarm_dict, rule_dict)
                except Exception as e:
                    log.warning(f"通知分发失败: {e}")

            return {
                "alarm_id": alarm_id,
                "alarm_created": True,
                "rule_matched": rule.name if rule else None,
            }

        except Exception as e:
            log.error(f"创建告警记录失败: {e}")
            return {"alarm_created": False, "error": str(e)}
