from collections.abc import Sequence
from datetime import datetime
from typing import Any

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.base_crud import CRUDBase
from app.core.exceptions import CustomException

from .model import EdgeDeviceModel
from .schema import EdgeDeviceCreateSchema, EdgeDeviceOutSchema, EdgeDeviceUpdateSchema


def capability_satisfies(capabilities: dict, requirement: dict) -> tuple[bool, str]:
    """校验设备能力是否满足布控需求。

    参数:
    - capabilities (dict): 设备能力清单。
    - requirement (dict): 需求，含 `model_family`/`backend`/`running_channels`。

    返回:
    - tuple[bool, str]: `(是否满足, 不满足原因)`；满足时原因为空串。
    """
    cap = capabilities or {}
    fam = requirement.get("model_family")
    if fam and fam not in (cap.get("model_families") or []):
        return False, f"设备不支持模型族 {fam}"
    be = requirement.get("backend")
    if be and be not in (cap.get("backends") or []):
        return False, f"设备不支持后端 {be}"
    maxc = int(cap.get("max_channels") or 0)
    running = int(requirement.get("running_channels") or 0)
    if maxc and running >= maxc:
        return False, f"设备并发布控路数已满 ({running}/{maxc})"
    return True, ""


def extract_device_code(body: dict) -> str:
    """从心跳载荷取设备编码：优先 `code`，兼容 Agent 的 `edge_code`。"""
    return str(body.get("code") or body.get("edge_code") or "").strip()


class EdgeCRUD(CRUDBase[EdgeDeviceModel, EdgeDeviceCreateSchema, EdgeDeviceUpdateSchema]):
    """边缘设备数据层。"""

    def __init__(self, auth: AuthSchema) -> None:
        self.auth = auth
        super().__init__(model=EdgeDeviceModel, auth=auth)

    async def get_by_id_crud(self, id: int) -> EdgeDeviceModel | None:
        return await self.get(id=id)

    async def get_list_crud(self, search: dict | None = None, order_by: list[dict[str, str]] | None = None) -> Sequence[EdgeDeviceModel]:
        return await self.list(search=search, order_by=order_by)


class EdgeService:
    """边缘设备业务层。"""

    capability_satisfies = staticmethod(capability_satisfies)

    @classmethod
    async def get_edge_list_service(cls, auth: AuthSchema, search: Any | None = None, order_by: list[dict[str, str]] | None = None) -> list[dict]:
        items = await EdgeCRUD(auth).get_list_crud(
            search=search.__dict__ if search else None,
            order_by=order_by,
        )
        return [EdgeDeviceOutSchema.model_validate(item).model_dump() for item in items]

    @classmethod
    async def get_edge_detail_service(cls, auth: AuthSchema, id: int) -> dict:
        item = await EdgeCRUD(auth).get_by_id_crud(id=id)
        if not item:
            raise CustomException(msg="边缘设备不存在", code=404, status_code=404)
        return EdgeDeviceOutSchema.model_validate(item).model_dump()

    @classmethod
    async def create_edge_service(cls, data: EdgeDeviceCreateSchema, auth: AuthSchema) -> dict:
        existing = await EdgeCRUD(auth).get(code=data.code)
        if existing:
            raise CustomException(msg=f"设备编码已存在: {data.code}")
        item = await EdgeCRUD(auth).create(data=data)
        return EdgeDeviceOutSchema.model_validate(item).model_dump()

    @classmethod
    async def update_edge_service(cls, id: int, data: EdgeDeviceUpdateSchema, auth: AuthSchema) -> dict:
        item = await EdgeCRUD(auth).get_by_id_crud(id=id)
        if not item:
            raise CustomException(msg="边缘设备不存在")
        updated = await EdgeCRUD(auth).update(id=id, data=data)
        return EdgeDeviceOutSchema.model_validate(updated).model_dump()

    @classmethod
    async def delete_edge_service(cls, ids: list[int], auth: AuthSchema) -> None:
        await EdgeCRUD(auth).delete(ids=ids)

    @classmethod
    async def heartbeat(cls, body: dict) -> dict:
        """按 `code` upsert 设备心跳：更新能力/指标/在线状态/最后心跳时间。"""
        from sqlalchemy import select
        from sqlalchemy.exc import IntegrityError

        from app.core.database import async_db_session

        code = extract_device_code(body)
        if not code:
            raise CustomException(msg="设备编码不能为空", code=400)

        now = datetime.now()
        capabilities = body.get("capabilities")
        metrics = body.get("metrics")
        control_url = body.get("control_url")

        def _apply(existing: EdgeDeviceModel) -> None:
            # 将本次心跳写入已存在的设备行
            if capabilities is not None:
                existing.capabilities = capabilities
            existing.metrics = metrics or {}
            existing.status = "online"
            existing.last_heartbeat = now
            if control_url:
                existing.control_url = control_url

        async with async_db_session.begin() as session:
            existing = (
                await session.execute(
                    select(EdgeDeviceModel).where(EdgeDeviceModel.code == code)
                )
            ).scalars().first()

            if existing:
                _apply(existing)
                device_id = existing.id
            else:
                obj = EdgeDeviceModel(
                    name=str(body.get("name") or code),
                    code=code,
                    control_url=control_url,
                    capabilities=capabilities or {},
                    metrics=metrics or {},
                    status="online",
                    last_heartbeat=now,
                    description=body.get("description"),
                )
                try:
                    # 保存点隔离：并发首次心跳的唯一键冲突只回滚本次插入
                    async with session.begin_nested():
                        session.add(obj)
                        await session.flush()
                    device_id = obj.id
                except IntegrityError:
                    # 已被并发会话抢先插入，回查后按更新处理
                    existing = (
                        await session.execute(
                            select(EdgeDeviceModel).where(EdgeDeviceModel.code == code)
                        )
                    ).scalars().first()
                    if not existing:
                        raise
                    _apply(existing)
                    device_id = existing.id

        return {"id": device_id, "code": code, "status": "online"}
