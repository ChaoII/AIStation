import base64
import logging
from datetime import datetime
from pathlib import Path

from app.config.setting import settings

log = logging.getLogger(__name__)


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
            rule = result.scalar_one_or_none()

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

            # Async notification
            if rule:
                try:
                    from app.api.v1.module_system.auth.schema import AuthSchema
                    from app.utils.notification import dispatch_notification

                    auth = AuthSchema(user=None, permissions=None, db=None)
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
                    import asyncio
                    asyncio.ensure_future(dispatch_notification(auth, alarm_dict, rule_dict))
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
