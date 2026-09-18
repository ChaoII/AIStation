from sqlalchemy import and_, func, select

from app.config.setting import settings
from app.core.database import async_db_session
from app.core.logger import log

from ..annotation.model import AnnotationRecordModel
from ..dataset.model import AnnotationImageModel
from .model import AnnotationTaskModel


class TaskService:

    @classmethod
    async def update_progress(cls, task_id: int, auth=None) -> dict:
        from datetime import datetime

        async with async_db_session.begin() as db:
            task = await db.get(AnnotationTaskModel, task_id)
            if not task:
                log.warning(f"update_progress: task {task_id} not found")
                return {}
            result = await cls._calc_progress(db, task_id, task.dataset_id)
            if result:
                task.progress = result["progress"]
                task.status = result["status"]
                if result["progress"] >= 100:
                    task.completed_at = task.completed_at or datetime.now()
                else:
                    task.completed_at = None
            return result

    @classmethod
    async def get_task_progress(cls, task_id: int, auth) -> dict:
        async with async_db_session() as db:
            task = await db.get(AnnotationTaskModel, task_id)
            if not task:
                raise ValueError("任务不存在")
            return await cls._calc_progress(db, task_id, task.dataset_id)

    @classmethod
    async def _calc_progress(cls, db, task_id: int, dataset_id: int) -> dict:
        # Total images in dataset（排除软删图片）
        total = await db.scalar(
            select(func.count(AnnotationImageModel.id))
            .where(
                AnnotationImageModel.dataset_id == dataset_id,
                AnnotationImageModel.is_deleted == False,  # noqa: E712
            )
        ) or 0

        # Annotated images for THIS task only (count distinct images in annotation_record
        # where the latest version has non-empty annotation_data)
        if total == 0:
            return {"total_images": 0, "annotated_images": 0, "progress": 0, "status": "pending"}

        # Subquery: for each image, find the latest annotation record version for this task
        max_v = select(
            AnnotationRecordModel.image_id,
            func.max(AnnotationRecordModel.version).label("max_v")
        ).where(
            AnnotationRecordModel.task_id == task_id
        ).group_by(AnnotationRecordModel.image_id).subquery()

        # SQLite 无 jsonb_array_length，退化为 json_array_length（测试库兼容）
        json_length = (
            func.json_array_length
            if settings.DATABASE_TYPE == "sqlite"
            else func.jsonb_array_length
        )

        # Join to get the actual records and count those with non-empty annotation_data
        annotated = await db.scalar(
            select(func.count(func.distinct(AnnotationRecordModel.image_id)))
            .select_from(AnnotationRecordModel)
            .join(max_v, and_(
                AnnotationRecordModel.image_id == max_v.c.image_id,
                AnnotationRecordModel.version == max_v.c.max_v,
            ))
            .where(
                AnnotationRecordModel.task_id == task_id,
                AnnotationRecordModel.annotation_data.isnot(None),
                json_length(AnnotationRecordModel.annotation_data) > 0,
            )
        ) or 0

        pct = int(annotated / total * 100) if total > 0 else 0
        status = "COMPLETED" if pct >= 100 else "IN_PROGRESS" if pct > 0 else "PENDING"

        return {
            "total_images": total,
            "annotated_images": annotated,
            "progress": pct,
            "status": status.lower(),
        }

    @classmethod
    async def _calc_progress_bulk(cls, db, items: list[dict]) -> dict[int, dict]:
        """批量计算本页任务的进度与状态（只读，单次聚合，不写库）。

        输入 ``items`` 为本页任务字典（含 ``id`` / ``dataset_id``），返回
        ``{task_id: {"progress": int, "status": str}}``。沿用 ``enrich_dataset_list``
        的 max(version) join 逻辑，避免逐条 ``_calc_progress`` 的 N+1 查询。
        """
        if not items:
            return {}
        ds_ids = {it["dataset_id"] for it in items}
        total_rows = await db.execute(
            select(AnnotationImageModel.dataset_id, func.count(AnnotationImageModel.id))
            .where(
                AnnotationImageModel.dataset_id.in_(ds_ids),
                AnnotationImageModel.is_deleted == False,  # noqa: E712
            )
            .group_by(AnnotationImageModel.dataset_id)
        )
        totals = dict(total_rows.fetchall())

        task_ids = [it["id"] for it in items]
        ann: dict[int, int] = {}
        if task_ids:
            max_v = (
                select(
                    AnnotationRecordModel.task_id.label("task_id"),
                    AnnotationRecordModel.image_id.label("image_id"),
                    func.max(AnnotationRecordModel.version).label("mv"),
                )
                .where(AnnotationRecordModel.task_id.in_(task_ids))
                .group_by(AnnotationRecordModel.task_id, AnnotationRecordModel.image_id)
                .subquery()
            )
            json_length = (
                func.json_array_length
                if settings.DATABASE_TYPE == "sqlite"
                else func.jsonb_array_length
            )
            ann_rows = await db.execute(
                select(AnnotationRecordModel.task_id, func.count())
                .select_from(AnnotationRecordModel)
                .join(
                    max_v,
                    and_(
                        AnnotationRecordModel.task_id == max_v.c.task_id,
                        AnnotationRecordModel.image_id == max_v.c.image_id,
                        AnnotationRecordModel.version == max_v.c.mv,
                    ),
                )
                .where(
                    AnnotationRecordModel.annotation_data.isnot(None),
                    json_length(AnnotationRecordModel.annotation_data) > 0,
                )
                .group_by(AnnotationRecordModel.task_id)
            )
            ann = dict(ann_rows.fetchall())

        out: dict[int, dict] = {}
        for item in items:
            total = totals.get(item["dataset_id"], 0)
            pct = int(ann.get(item["id"], 0) / total * 100) if total > 0 else 0
            status = "completed" if pct >= 100 else "in_progress" if pct > 0 else "pending"
            out[item["id"]] = {"progress": pct, "status": status}
        return out

    @classmethod
    async def ensure_annotation_access(cls, user_ids: list[int]) -> None:
        """Grant annotation menu permissions to users (task assignees)."""
        if not user_ids:
            return
        from sqlalchemy import and_, exists, select

        from app.api.v1.module_system.menu.model import MenuModel
        from app.api.v1.module_system.role.model import RoleMenusModel, RoleModel
        from app.api.v1.module_system.user.model import UserRolesModel
        from app.core.database import async_db_session

        async with async_db_session.begin() as db:
            role = (await db.execute(
                select(RoleModel).where(RoleModel.code == "ANNOTATOR")
            )).scalar_one_or_none()

            if not role:
                role = RoleModel(name="标注员", code="ANNOTATOR", status="0", order=99, data_scope=3)
                db.add(role)
                await db.flush()

            # Ensure all needed menus are assigned to the role
            needed_perms = [
                # Backend API permissions
                "annotation:dataset:query", "annotation:dataset:create", "annotation:dataset:update", "annotation:dataset:delete",
                "annotation:task:query", "annotation:task:create", "annotation:task:update", "annotation:task:delete",
                "annotation:workbench:query", "annotation:stats:query",
                # Frontend button permissions
                "module_annotation:dataset:query", "module_annotation:dataset:create", "module_annotation:dataset:update",
                "module_annotation:dataset:delete", "module_annotation:dataset:upload",
                "module_annotation:task:query", "module_annotation:task:create", "module_annotation:task:update",
                "module_annotation:task:delete", "module_annotation:task:patch", "module_annotation:task:workbench",
                "module_annotation:stats:query",
                # System query permissions
                "module_system:user:query", "module_system:role:query",
            ]
            existing_menu_ids = set(
                (await db.execute(
                    select(RoleMenusModel.menu_id).where(RoleMenusModel.role_id == role.id)
                )).scalars().all()
            )
            menus_to_add = await db.execute(
                select(MenuModel).where(
                    and_(MenuModel.permission.in_(needed_perms),
                         ~MenuModel.id.in_(existing_menu_ids))
                )
            )
            for menu in menus_to_add.scalars():
                db.add(RoleMenusModel(role_id=role.id, menu_id=menu.id))

            for uid in user_ids:
                has_role = await db.scalar(
                    select(exists().where(
                        and_(UserRolesModel.user_id == uid, UserRolesModel.role_id == role.id)
                    ))
                )
                if not has_role:
                    db.add(UserRolesModel(user_id=uid, role_id=role.id))

            log.info(f"Granted ANNOTATOR role to users: {user_ids}")

    @classmethod
    async def check_workbench_access(cls, task_id: int, user_id: int, is_superuser: bool) -> bool:
        """检查用户是否有权限访问该任务的工作台."""
        if is_superuser:
            return True
        async with async_db_session() as db:
            task = await db.get(AnnotationTaskModel, task_id)
            if not task:
                return False
            if task.created_id == user_id:
                return True
            assignees = task.assignees or []
            return user_id in assignees
