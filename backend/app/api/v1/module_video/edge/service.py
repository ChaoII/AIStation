from collections.abc import Sequence
from datetime import datetime
from typing import Any

from app.api.v1.module_system.auth.schema import AuthSchema
from app.api.v1.module_video.inference.snapshot import resolve_snapshot_url
from app.config.setting import settings
from app.core.base_crud import CRUDBase
from app.core.exceptions import CustomException
from app.utils.url_guard import UnsafeUrlError, validate_outbound_url

from .model import EdgeDeviceModel, EdgeEventModel
from .schema import EdgeDeviceCreateSchema, EdgeDeviceOutSchema, EdgeDeviceUpdateSchema


def capability_satisfies(capabilities: dict, requirement: dict) -> tuple[bool, str]:
    """校验设备能力是否满足布控需求。

    参数:
    - capabilities (dict): 设备能力清单。
    - requirement (dict): 需求，含 `model_families`（列表，需全部具备）或兼容旧的
      `model_family`（单个），以及 `backend`/`running_channels`。

    返回:
    - tuple[bool, str]: `(是否满足, 不满足原因)`；满足时原因为空串。
    """
    cap = capabilities or {}
    available = cap.get("model_families") or []
    # 支持一次要求多个模型族（场景目录 pipeline 可能依赖多个），必须全部具备
    for fam in requirement.get("model_families") or []:
        if fam not in available:
            have = "、".join(str(x) for x in available) or "无"
            return False, f"缺少所需模型族 {fam}（设备仅支持：{have}）"
    # 兼容旧的单模型族用法
    fam = requirement.get("model_family")
    if fam and fam not in available:
        have = "、".join(str(x) for x in available) or "无"
        return False, f"缺少所需模型族 {fam}（设备仅支持：{have}）"
    be = requirement.get("backend")
    if be:
        backs = [str(x) for x in (cap.get("backends") or [])]
        if not backs:
            return False, f"设备未上报可用推理后端，无法下发后端 {be}"
        if be not in backs:
            return False, f"设备不支持后端 {be}（设备可用后端：{'、'.join(backs)}）"
    maxc = int(cap.get("max_channels") or 0)
    running = int(requirement.get("running_channels") or 0)
    if maxc and running >= maxc:
        return False, f"设备并发布控路数已满 ({running}/{maxc})"
    return True, ""


def extract_device_code(body: dict) -> str:
    """从心跳载荷取设备编码：优先 `code`，兼容 Agent 的 `edge_code`。"""
    return str(body.get("code") or body.get("edge_code") or "").strip()


def _event_conditions(
    *,
    camera_id: int | None = None,
    task_id: int | None = None,
    algorithm_type: str | None = None,
    matched: bool | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    keyword: str | None = None,
) -> list:
    """构造边缘事件筛选条件（含软删过滤）；``keyword`` 对 objects 文本模糊。"""
    from sqlalchemy import Text, cast

    conditions = [EdgeEventModel.is_deleted == False]
    if camera_id is not None:
        conditions.append(EdgeEventModel.camera_id == camera_id)
    if task_id is not None:
        conditions.append(EdgeEventModel.task_id == task_id)
    if algorithm_type:
        conditions.append(EdgeEventModel.algorithm_type == algorithm_type)
    if matched is not None:
        conditions.append(EdgeEventModel.matched.is_(bool(matched)))
    if start_time is not None:
        conditions.append(EdgeEventModel.ts >= start_time)
    if end_time is not None:
        conditions.append(EdgeEventModel.ts <= end_time)
    if keyword:
        # JSONB 文本化后 ILIKE：值经参数绑定，天然防注入（%/_ 由用户自控，属模糊匹配语义）
        conditions.append(cast(EdgeEventModel.objects, Text).ilike(f"%{keyword}%"))
    return conditions


def _event_order_columns(order_by: list[dict[str, str]] | None) -> list:
    """按前端/分页入参生成排序列，默认按 id 倒序（最新在前）。"""
    from sqlalchemy import asc, desc

    columns = []
    for spec in order_by or []:
        for field, direction in spec.items():
            column = getattr(EdgeEventModel, field, None)
            if column is None:
                continue
            columns.append(desc(column) if str(direction).lower() == "desc" else asc(column))
    return columns or [desc(EdgeEventModel.id)]


def _event_object_labels(objects, limit: int = 10) -> list[str]:
    """从 objects 提取去重后的 label 摘要（供列表展示）。"""
    labels: list[str] = []
    for obj in objects or []:
        if isinstance(obj, dict):
            label = obj.get("label")
            if label and label not in labels:
                labels.append(label)
                if len(labels) >= limit:
                    break
    return labels


def _event_base_fields(row: EdgeEventModel) -> dict:
    """事件公共字段；仅暴露白名单列，``snapshot_data`` 不可能出现。"""
    objects = row.objects or []
    return {
        "id": row.id,
        "event_id": row.event_id,
        "edge_code": row.edge_code,
        "camera_id": row.camera_id,
        "task_id": row.task_id,
        "algorithm_type": row.algorithm_type,
        "ts": row.ts,
        "latency_ms": row.latency_ms,
        # snapshot_ref 保持原始存储值；snapshot_url 为归一化后的可取图地址（与告警侧一致）
        "snapshot_ref": row.snapshot_ref,
        "snapshot_url": resolve_snapshot_url(row.snapshot_ref),
        "matched": bool(row.matched),
        "matched_rule_id": row.matched_rule_id,
        "object_count": len(objects),
        "labels": _event_object_labels(objects),
        "created_time": row.created_time,
    }


def _event_item(row: EdgeEventModel) -> dict:
    """列表项（轻量摘要）。"""
    return _event_base_fields(row)


def _event_detail(row: EdgeEventModel) -> dict:
    """详情：全量 objects/detections/matched_leaves。"""
    data = _event_base_fields(row)
    data["objects"] = row.objects or []
    data["detections"] = row.detections or []
    data["matched_leaves"] = row.matched_leaves or []
    return data


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
    async def get_edge_event_page_service(
        cls,
        *,
        auth: AuthSchema,
        page_no: int = 1,
        page_size: int = 10,
        order_by: list[dict[str, str]] | None = None,
        camera_id: int | None = None,
        task_id: int | None = None,
        algorithm_type: str | None = None,
        matched: bool | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        keyword: str | None = None,
    ) -> dict:
        """边缘事件分页查询，返回项目标准分页结构与轻量列表项。"""
        from sqlalchemy import func, select

        from app.core.permission import Permission

        permission = Permission(model=EdgeEventModel, auth=auth)
        conditions = _event_conditions(
            camera_id=camera_id,
            task_id=task_id,
            algorithm_type=algorithm_type,
            matched=matched,
            start_time=start_time,
            end_time=end_time,
            keyword=keyword,
        )

        sql = (
            select(EdgeEventModel)
            .where(*conditions)
            .order_by(*_event_order_columns(order_by))
        )
        sql = await permission.filter_query(sql)
        count_sql = await permission.filter_query(
            select(func.count(EdgeEventModel.id)).where(*conditions)
        )

        total = int((await auth.db.execute(count_sql)).scalar() or 0)
        offset = (page_no - 1) * page_size
        rows = (await auth.db.execute(sql.offset(offset).limit(page_size))).scalars().all()
        return {
            "page_no": page_no,
            "page_size": page_size,
            "total": total,
            "has_next": offset + page_size < total,
            "items": [_event_item(row) for row in rows],
        }

    @classmethod
    async def get_edge_event_detail_service(cls, *, auth: AuthSchema, id: int) -> dict:
        """边缘事件详情（全量 objects/detections/matched_leaves）；不存在返回 404。"""
        from sqlalchemy import select

        from app.core.permission import Permission

        sql = select(EdgeEventModel).where(
            EdgeEventModel.id == id,
            EdgeEventModel.is_deleted == False,
        )
        sql = await Permission(model=EdgeEventModel, auth=auth).filter_query(sql)
        row = (await auth.db.execute(sql)).scalars().first()
        if not row:
            raise CustomException(msg="边缘事件不存在", code=404, status_code=404)
        return _event_detail(row)

    @classmethod
    async def create_edge_service(cls, data: EdgeDeviceCreateSchema, auth: AuthSchema) -> dict:
        from sqlalchemy import select

        from app.core.database import async_db_session

        crud = EdgeCRUD(auth)
        # 软删行仍占用 code 的唯一键：CRUDBase.get 会过滤 is_deleted，故直接查询连软删行一并取出，
        # 否则同码重建会撞 UniqueViolationError 返回 500。
        async with async_db_session() as session:
            row = (
                await session.execute(
                    select(EdgeDeviceModel).where(EdgeDeviceModel.code == data.code)
                )
            ).scalars().first()
            row_id = row.id if row is not None else None
            row_deleted = bool(row.is_deleted) if row is not None else False

        if row_id is not None:
            if not row_deleted:
                raise CustomException(msg=f"设备编码已存在: {data.code}")
            # 命中同码软删行：先恢复再按本次入参覆盖，复用同一行（保持 id 稳定）
            await crud.restore(ids=[row_id])
            updated = await crud.update(id=row_id, data=EdgeDeviceUpdateSchema(**data.model_dump()))
            return EdgeDeviceOutSchema.model_validate(updated).model_dump()

        item = await crud.create(data=data)
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
    async def get_task_snapshot_service(cls, device_id: int, task_id: int, auth: AuthSchema) -> bytes:
        """经边缘设备控制面代理取某任务最新帧 JPEG。"""
        from .agent_client import EdgeAgentClient

        device = await EdgeCRUD(auth).get_by_id_crud(id=device_id)
        if not device:
            raise CustomException(msg="边缘设备不存在", code=404, status_code=404)
        if not (device.control_url or "").strip():
            raise CustomException(msg="边缘设备未配置控制面地址", code=400, status_code=400)
        client = EdgeAgentClient(device.control_url, device.secret)
        return await client.fetch_snapshot(task_id)

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
        # SSRF 防护（审计 #12）：心跳可写 control_url，落库前先校验，阻止内网探测/元数据访问
        if control_url:
            try:
                validate_outbound_url(
                    control_url,
                    block_private=settings.EDGE_CONTROL_URL_BLOCK_PRIVATE,
                    allowed_hosts=set(settings.EDGE_CONTROL_URL_ALLOWED_HOSTS) or None,
                )
            except UnsafeUrlError as e:
                raise CustomException(
                    msg=f"控制面地址不安全：{e}", code=400, status_code=400
                ) from e

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
