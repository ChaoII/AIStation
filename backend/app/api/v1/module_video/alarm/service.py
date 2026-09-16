from datetime import datetime
from typing import Any

from app.api.v1.module_system.auth.schema import AuthSchema
from app.api.v1.module_video.scene.compile import RuleCompileError, compile_rule
from app.core.exceptions import CustomException

from .schema import (
    AlarmRecordConfirmSchema,
    AlarmRecordOutSchema,
    AlarmRuleCreateSchema,
    AlarmRuleOutSchema,
    AlarmRuleUpdateSchema,
)


def _compile_or_raise(
    scene_type: str | None,
    params: dict | None,
    conditions: dict | None,
    *,
    scope: str | None = None,
) -> dict:
    """写库前编译条件树：把场景参数展开进叶子，非法条件映射为 HTTP 400。

    ``scope`` 透传到编译层，保证相机作用域误用 group_* 叶子时同样返回 400。
    """
    try:
        return compile_rule(scene_type, params, conditions, scope=scope)
    except RuleCompileError as e:
        raise CustomException(msg=f"规则条件非法：{e}", code=400, status_code=400) from e


def _validate_scope(camera_id: int | None, group_id: int | None) -> None:
    """作用域校验：camera_id 与 group_id 恰有其一非空，否则 HTTP 400。"""
    if (camera_id is None) == (group_id is None):
        raise CustomException(
            msg="规则作用域非法：camera_id 与 group_id 必须且只能指定一个",
            code=400,
            status_code=400,
        )


def _validate_rollout(rollout: dict | None) -> None:
    """灰度配置校验：percent 0-100；名单为相机 id 列表且互斥。非法 → 400。"""
    if not rollout:
        return
    if not isinstance(rollout, dict):
        raise CustomException(msg="灰度配置非法：必须为对象", code=400, status_code=400)
    percent = rollout.get("percent")
    if percent is not None:
        if isinstance(percent, bool) or not isinstance(percent, int) or not (0 <= percent <= 100):
            raise CustomException(
                msg="灰度配置非法：percent 必须为 0-100 的整数", code=400, status_code=400
            )
    wl, bl = rollout.get("whitelist"), rollout.get("blacklist")
    for name, lst in (("whitelist", wl), ("blacklist", bl)):
        if lst is None:
            continue
        if not isinstance(lst, list) or any(
            isinstance(x, bool) or not isinstance(x, int) or x <= 0 for x in lst
        ):
            raise CustomException(
                msg=f"灰度配置非法：{name} 必须为相机 id 正整数列表", code=400, status_code=400
            )
    if wl and bl and set(wl) & set(bl):
        raise CustomException(
            msg="灰度配置非法：白名单与黑名单不得同时包含同一相机", code=400, status_code=400
        )


class AlarmService:

    @classmethod
    async def get_rule_list_service(cls, auth: AuthSchema, search: Any | None = None) -> list[dict]:
        from .crud import AlarmRuleCRUD
        rules = await AlarmRuleCRUD(auth).get_list_crud(search=search.__dict__ if search else None)
        return [AlarmRuleOutSchema.model_validate(r).model_dump() for r in rules]

    @classmethod
    async def get_rule_detail_service(cls, auth: AuthSchema, id: int) -> dict:
        """按 id 精确查询单条规则；不存在返回 404。

        前端「编辑」不再依赖仅取前 N 条的列表匹配（规则数 >N 时会把编辑误判为新建）。
        """
        from .crud import AlarmRuleCRUD
        rule = await AlarmRuleCRUD(auth).get_by_id_crud(id=id)
        if not rule:
            raise CustomException(msg="告警规则不存在", code=404, status_code=404)
        return AlarmRuleOutSchema.model_validate(rule).model_dump()

    @classmethod
    async def create_rule_service(cls, data: AlarmRuleCreateSchema, auth: AuthSchema) -> dict:
        from .crud import AlarmRuleCRUD
        # 写库前完成条件编译校验，非法条件直接拒绝（HTTP 400）
        payload = data.model_dump()
        # 作用域校验：camera_id 与 group_id 恰有其一（都空/都填 → 400）
        _validate_scope(payload.get("camera_id"), payload.get("group_id"))
        # 灰度配置校验：percent 范围、白黑名单合法性与互斥（非法 → 400）
        _validate_rollout(payload.get("rollout"))
        # 编译层需知作用域：仅相机组作用域允许 group_* 聚合叶子
        scope = "group" if payload.get("group_id") is not None else "camera"
        payload["conditions"] = _compile_or_raise(
            payload.get("alarm_type"), payload.get("params"), payload.get("conditions"), scope=scope
        )
        new_rule = await AlarmRuleCRUD(auth).create(data=payload)
        return AlarmRuleOutSchema.model_validate(new_rule).model_dump()

    @classmethod
    async def update_rule_service(cls, id: int, data: AlarmRuleUpdateSchema, auth: AuthSchema) -> dict:
        from .crud import AlarmRuleCRUD
        rule = await AlarmRuleCRUD(auth).get_by_id_crud(id=id)
        if not rule:
            raise CustomException(msg="告警规则不存在")
        payload = data.model_dump(exclude_unset=True)
        # 局部更新：按「合并库中现值后的结果态」校验作用域，避免仅改名称被误判
        camera_id = payload["camera_id"] if "camera_id" in payload else rule.camera_id
        group_id = payload["group_id"] if "group_id" in payload else rule.group_id
        _validate_scope(camera_id, group_id)
        # 灰度配置校验同样按「合并库中现值后的结果态」，避免仅改其他字段被误判
        rollout = payload["rollout"] if "rollout" in payload else rule.rollout
        _validate_rollout(rollout)
        # 编译层需知（合并后的）作用域：仅相机组作用域允许 group_* 聚合叶子
        scope = "group" if group_id is not None else "camera"
        # 仅在本次涉及条件/参数/告警类型时重编译；未提供的字段回退库中现值，
        # 避免仅改名称的局部更新把既有条件清空
        if {"conditions", "params", "alarm_type"} & payload.keys():
            payload["conditions"] = _compile_or_raise(
                payload.get("alarm_type", rule.alarm_type),
                payload.get("params", rule.params),
                payload.get("conditions", rule.conditions),
                scope=scope,
            )
        updated = await AlarmRuleCRUD(auth).update(id=id, data=payload)
        return AlarmRuleOutSchema.model_validate(updated).model_dump()

    @classmethod
    async def delete_rule_service(cls, ids: list[int], auth: AuthSchema) -> None:
        from .crud import AlarmRuleCRUD
        await AlarmRuleCRUD(auth).delete(ids=ids)

    @classmethod
    async def get_record_list_service(
        cls,
        auth: AuthSchema,
        page_no: int = 1,
        page_size: int = 10,
        search: Any | None = None,
    ) -> dict:
        """告警记录列表：数据库分页（LIMIT/OFFSET + COUNT），不再全表载入内存。

        参数:
        - auth (AuthSchema): 认证信息。
        - page_no (int): 页码（从 1 开始）。
        - page_size (int): 每页数量。
        - search (Any | None): 查询条件对象。

        返回:
        - dict: `CRUDBase.page` 约定的分页结构。
        """
        from .crud import AlarmRecordCRUD
        offset = max(page_no - 1, 0) * page_size
        return await AlarmRecordCRUD(auth).page(
            offset=offset,
            limit=page_size,
            order_by=[{"alarm_time": "desc"}],
            search=search.__dict__ if search else {},
            out_schema=AlarmRecordOutSchema,
        )

    @classmethod
    async def get_realtime_alarms_service(cls, auth: AuthSchema) -> list[dict]:
        """实时告警：SQL 侧 LIMIT 100（原实现先取全量再切片）。"""
        from .crud import AlarmRecordCRUD
        result = await AlarmRecordCRUD(auth).page(
            offset=0,
            limit=100,
            order_by=[{"alarm_time": "desc"}],
            search={"status": "PENDING"},
            out_schema=AlarmRecordOutSchema,
        )
        return result["items"]

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
