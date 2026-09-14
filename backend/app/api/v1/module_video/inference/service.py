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


def _match_conditions(conditions: dict | None, detections: list[dict]) -> bool:
    """评估规则条件树；空/None 视为命中。

    叶子支持 attribute：{"subject":"attribute","field":名,"op":"lt|gt|le|ge|eq","value":数}。
    事件里 attributes 为 {属性名: 分数}（分数=具有该属性的概率）；违规=分数低于阈值。
    OCR 文本叶子：
    - text_match：{"subject":"text_match","regex":"..."}，任一 detection.text 命中正则即命中；
      非法正则视为不命中。
    - ocr_label：{"subject":"ocr_label","contains":"..."}，任一 detection.text 包含子串即命中。
    其它叶子后续扩展；未知叶子不命中。
    本函数对异常输入（JSON null / 非数值）一律按不命中处理，绝不向上抛异常，
    避免单条脏规则导致整个告警事件被丢弃。
    """
    if not conditions:
        return True

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
        return [d["text"] for d in detections or [] if isinstance(d.get("text"), str)]

    def eval_leaf(leaf: dict) -> bool:
        subject = leaf.get("subject")
        if subject == "attribute":
            field = leaf.get("field")
            op = leaf.get("op", "eq")
            value = _to_float(leaf.get("value"))
            if value is None:
                return False
            for d in detections or []:
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
        return False

    def eval_node(node: dict) -> bool:
        # 逻辑节点（and/or/not）与属性叶子都带 "op"，用逻辑算子集合区分：
        # 叶子 op 为 lt/gt/le/ge/eq，若误当逻辑节点会直接不命中。
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
