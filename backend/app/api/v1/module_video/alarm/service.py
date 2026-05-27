import asyncio
import logging
from datetime import datetime
from typing import Any

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.exceptions import CustomException

from .schema import (
    AlarmRecordConfirmSchema,
    AlarmRecordOutSchema,
    AlarmRuleCreateSchema,
    AlarmRuleOutSchema,
    AlarmRuleUpdateSchema,
)

log = logging.getLogger(__name__)


class AlarmService:

    @classmethod
    async def get_rule_list_service(cls, auth: AuthSchema, search: Any | None = None) -> list[dict]:
        from .crud import AlarmRuleCRUD
        rules = await AlarmRuleCRUD(auth).get_list_crud(search=search.__dict__ if search else None)
        return [AlarmRuleOutSchema.model_validate(r).model_dump() for r in rules]

    @classmethod
    async def create_rule_service(cls, data: AlarmRuleCreateSchema, auth: AuthSchema) -> dict:
        from .crud import AlarmRuleCRUD
        new_rule = await AlarmRuleCRUD(auth).create(data=data)
        return AlarmRuleOutSchema.model_validate(new_rule).model_dump()

    @classmethod
    async def update_rule_service(cls, id: int, data: AlarmRuleUpdateSchema, auth: AuthSchema) -> dict:
        from .crud import AlarmRuleCRUD
        rule = await AlarmRuleCRUD(auth).get_by_id_crud(id=id)
        if not rule:
            raise CustomException(msg="告警规则不存在")
        updated = await AlarmRuleCRUD(auth).update(id=id, data=data)
        return AlarmRuleOutSchema.model_validate(updated).model_dump()

    @classmethod
    async def delete_rule_service(cls, ids: list[int], auth: AuthSchema) -> None:
        from .crud import AlarmRuleCRUD
        await AlarmRuleCRUD(auth).delete(ids=ids)

    @classmethod
    async def get_record_list_service(cls, auth: AuthSchema, search: Any | None = None) -> list[dict]:
        from .crud import AlarmRecordCRUD
        records = await AlarmRecordCRUD(auth).get_list_crud(
            search=search.__dict__ if search else None,
            order_by=[{"alarm_time": "desc"}]
        )
        return [AlarmRecordOutSchema.model_validate(r).model_dump() for r in records]

    @classmethod
    async def get_realtime_alarms_service(cls, auth: AuthSchema) -> list[dict]:
        from .crud import AlarmRecordCRUD
        records = await AlarmRecordCRUD(auth).get_list_crud(
            search={"status": "PENDING"},
            order_by=[{"alarm_time": "desc"}]
        )
        return [AlarmRecordOutSchema.model_validate(r).model_dump() for r in records[:100]]

    @classmethod
    async def confirm_alarm_service(cls, id: int, data: AlarmRecordConfirmSchema, auth: AuthSchema) -> dict:
        from .crud import AlarmRecordCRUD
        record = await AlarmRecordCRUD(auth).get(id=id)
        if not record:
            raise CustomException(msg="告警记录不存在")
        from app.api.v1.module_system.user.crud import UserCRUD
        user = await UserCRUD(auth).get_by_id_crud(id=auth.user.id)
        updated = await AlarmRecordCRUD(auth).update(id=id, data={
            "status": data.status,
            "confirm_time": datetime.now(),
            "confirm_user": user.name if user else "",
        })
        return AlarmRecordOutSchema.model_validate(updated).model_dump()

    @classmethod
    async def delete_record_service(cls, ids: list[int], auth: AuthSchema) -> None:
        from .crud import AlarmRecordCRUD
        await AlarmRecordCRUD(auth).delete(ids=ids)

    @classmethod
    async def create_alarm_record(cls, auth: AuthSchema, data: dict) -> dict:
        from .crud import AlarmRecordCRUD
        new_record = await AlarmRecordCRUD(auth).create(data=data)
        result = AlarmRecordOutSchema.model_validate(new_record).model_dump()
        # Dispatch notification asynchronously
        rule = None
        if data.get("rule_id"):
            rule = await AlarmService.get_rule_detail_service(auth, data["rule_id"])
        try:
            from app.utils.notification import dispatch_notification
            asyncio.ensure_future(dispatch_notification(auth, result, rule))
        except Exception as e:
            log.warning("Failed to dispatch notification: %s", e)
        return result

    @classmethod
    async def get_rule_detail_service(cls, auth: AuthSchema, rule_id: int) -> dict | None:
        from .crud import AlarmRuleCRUD
        rule = await AlarmRuleCRUD(auth).get_by_id_crud(id=rule_id)
        return AlarmRuleOutSchema.model_validate(rule).model_dump() if rule else None
