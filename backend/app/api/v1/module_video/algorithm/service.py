from typing import Any

from sqlalchemy import select

from app.api.v1.module_system.auth.schema import AuthSchema
from app.api.v1.module_video.edge.agent_client import EdgeAgentClient
from app.api.v1.module_video.edge.orchestrator import EdgeOrchestrator, build_agent_task_config
from app.config.setting import settings
from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.logger import logger

from .crud import AlgorithmCRUD, AlgorithmTaskCRUD
from .model import AlgorithmModel, AlgorithmTaskModel
from .schema import (
    AlgorithmCreateSchema,
    AlgorithmOutSchema,
    AlgorithmTaskCreateSchema,
    AlgorithmTaskOutSchema,
    AlgorithmTaskUpdateSchema,
    AlgorithmUpdateSchema,
)


def _error_text(exc: Exception) -> str:
    """统一提取异常文本（CustomException 带 msg 属性）。"""
    return getattr(exc, "msg", None) or str(exc) or exc.__class__.__name__


# URL 路径段中会改变请求语义的保留字符与控制字符（审计 #15）
_PATH_UNSAFE_CHARS: frozenset[str] = frozenset("/\\?#%") | {
    chr(c) for c in range(0x20)
} | {chr(0x7F)}


def _encode_path_segment(segment: str) -> str:
    """仅对会改变路径语义的字符做百分号编码，保留中文等非 ASCII（向后兼容）。

    新写入的算法名已在 schema 层被拒绝包含 ``/``/``\\``/控制字符；本函数用于
    防御历史遗留非法名称，确保拼入 Agent 请求路径时语义不变。
    """
    if not segment:
        return ""
    return "".join(
        f"%{ord(ch):02X}" if ch in _PATH_UNSAFE_CHARS else ch for ch in segment
    )


class AlgorithmService:

    @classmethod
    async def get_algorithm_list_service(cls, auth: AuthSchema, search: Any | None = None, order_by: list[dict[str, str]] | None = None) -> list[dict]:
        items = await AlgorithmCRUD(auth).get_list_crud(
            search=search.__dict__ if search else None,
            order_by=order_by
        )
        return [AlgorithmOutSchema.model_validate(item).model_dump() for item in items]

    @classmethod
    async def create_algorithm_service(cls, data: AlgorithmCreateSchema, auth: AuthSchema) -> dict:
        item = await AlgorithmCRUD(auth).create(data=data)
        return AlgorithmOutSchema.model_validate(item).model_dump()

    @classmethod
    async def update_algorithm_service(cls, id: int, data: AlgorithmUpdateSchema, auth: AuthSchema) -> dict:
        item = await AlgorithmCRUD(auth).get_by_id_crud(id=id)
        if not item:
            raise CustomException(msg="算法不存在")

        # SP6-c：模型在"变更时"记录上一版本（回滚依据）。
        # 只有 model_path / version 真正变化时才写入对应的 previous_*，
        # 未变化的字段保持原值不动；仅改描述等无关字段不触碰 previous_*。
        values = data.model_dump(exclude_unset=True)
        if "model_path" in values and values["model_path"] != item.model_path:
            values["previous_model_path"] = item.model_path
        if "version" in values and values["version"] != item.version:
            values["previous_version"] = item.version

        updated = await AlgorithmCRUD(auth).update(id=id, data=values)
        return AlgorithmOutSchema.model_validate(updated).model_dump()

    @classmethod
    async def delete_algorithm_service(cls, ids: list[int], auth: AuthSchema) -> None:
        await AlgorithmCRUD(auth).delete(ids=ids)

    @classmethod
    async def get_task_list_service(cls, auth: AuthSchema, search: Any | None = None, order_by: list[dict[str, str]] | None = None) -> list[dict]:
        items = await AlgorithmTaskCRUD(auth).get_list_crud(
            search=search.__dict__ if search else None,
            order_by=order_by
        )
        return [AlgorithmTaskOutSchema.model_validate(item).model_dump() for item in items]

    @classmethod
    async def create_task_service(cls, data: AlgorithmTaskCreateSchema, auth: AuthSchema) -> dict:
        # 指定边缘设备时先做场景↔能力校验：把「创建成功但下发必失败」提前为清晰的 400
        await cls._precheck_edge_capability(data)
        item = await AlgorithmTaskCRUD(auth).create(data=data)
        return AlgorithmTaskOutSchema.model_validate(item).model_dump()

    @classmethod
    async def _precheck_edge_capability(cls, data: AlgorithmTaskCreateSchema) -> None:
        """创建任务前的边缘能力预检（仅当指定了边缘设备）。

        场景↔能力不匹配（如 FALL 需 pose、设备仅支持 det）在创建时即拒绝，报
        「该场景需要模型族 X，设备仅支持 Y」，而不是等到下发时才以通用错误失败。
        """
        edge_device_id = getattr(data, "edge_device_id", None)
        algorithm_id = getattr(data, "algorithm_id", None)
        if not edge_device_id or not algorithm_id:
            return
        from app.api.v1.module_video.edge.model import EdgeDeviceModel

        async with async_db_session() as session:
            device = (
                await session.execute(
                    select(EdgeDeviceModel).where(
                        EdgeDeviceModel.id == edge_device_id,
                        EdgeDeviceModel.is_deleted.is_(False),
                    )
                )
            ).scalar_one_or_none()
            algorithm = (
                await session.execute(
                    select(AlgorithmModel).where(
                        AlgorithmModel.id == algorithm_id,
                        AlgorithmModel.is_deleted.is_(False),
                    )
                )
            ).scalar_one_or_none()
        if device is None or algorithm is None:
            # 交由 CRUD 外键/存在性校验给出原始错误，避免此处掩盖
            return
        running = await EdgeOrchestrator._count_running(edge_device_id, exclude_id=0)
        ok, reason = EdgeOrchestrator._check_capability(device.capabilities, algorithm, running)
        if not ok:
            raise CustomException(msg=f"边缘设备能力不足：{reason}", code=400, status_code=400)

    @classmethod
    async def update_task_service(cls, id: int, data: AlgorithmTaskUpdateSchema, auth: AuthSchema) -> dict:
        item = await AlgorithmTaskCRUD(auth).get_by_id_crud(id=id)
        if not item:
            raise CustomException(msg="算法任务不存在")
        updated = await AlgorithmTaskCRUD(auth).update(id=id, data=data)
        return AlgorithmTaskOutSchema.model_validate(updated).model_dump()

    @classmethod
    async def delete_task_service(cls, ids: list[int], auth: AuthSchema) -> None:
        await AlgorithmTaskCRUD(auth).delete(ids=ids)

    # ──────────────────────────────────────────────
    #  SP6-c：模型热更新 / 回滚（下发到所有引用该算法的任务）
    # ──────────────────────────────────────────────

    @staticmethod
    async def _load_algorithm(id: int, auth: AuthSchema) -> AlgorithmModel | None:
        """加载算法；抽为独立方法便于测试替换。"""
        return await AlgorithmCRUD(auth).get_by_id_crud(id=id)

    @staticmethod
    async def _list_referencing_tasks(algorithm_id: int) -> list[AlgorithmTaskModel]:
        """枚举所有引用该算法的未删除任务（外键 video_algorithm_tasks.algorithm_id）。"""
        async with async_db_session() as session:
            stmt = select(AlgorithmTaskModel).where(
                AlgorithmTaskModel.algorithm_id == algorithm_id,
                AlgorithmTaskModel.is_deleted.is_(False),
            )
            return list((await session.execute(stmt)).scalars().all())

    @staticmethod
    async def _persist_algorithm_fields(algorithm_id: int, values: dict, auth: AuthSchema) -> None:
        """写回算法字段（previous_*/model_path/version）。"""
        await AlgorithmCRUD(auth).update(id=algorithm_id, data=values)

    @staticmethod
    async def _dispatch_task_model_update(task: AlgorithmTaskModel, algorithm: AlgorithmModel) -> dict:
        """向单个任务所属 Agent 下发指定模型的 ModelConfig 热更新。

        复用 `build_agent_task_config` 编译出的模型条目（保证载荷与下发时的形状一致），
        并复用 `EdgeOrchestrator._resolve_target` 解析控制面地址与密钥、
        `EdgeAgentClient` 负责鉴权与错误包装。
        """
        camera = getattr(task, "camera", None)
        if camera is None:
            raise ValueError("任务未关联摄像头")

        # 先解析目标设备，再用其上报能力协商模型条目（后端/设备），保证载荷与下发时一致
        control_url, device = await EdgeOrchestrator._resolve_target(task)
        if not control_url:
            raise RuntimeError("任务未配置边缘设备/本机 Agent，无法热更新")

        config = build_agent_task_config(
            task,
            camera,
            algorithm,
            events={},
            capabilities=getattr(device, "capabilities", None) if device is not None else None,
        )
        model_entry = next(
            (m for m in (config.get("models") or []) if m.get("name") == algorithm.name),
            None,
        )
        if model_entry is None:
            raise ValueError("未解析到算法模型配置")

        secret = device.secret if device is not None else settings.EDGE_CONTROL_TOKEN
        client = EdgeAgentClient(control_url, secret)
        # Agent 控制面：POST /api/v1/tasks/{task_id}/models/{name}/update（SP6-c 契约）
        # 名称作为路径段做编码，避免 / ? # 等改变请求语义（审计 #15）
        safe_name = _encode_path_segment(algorithm.name or "")
        result = await client._request(
            "POST",
            f"/api/v1/tasks/{task.id}/models/{safe_name}/update",
            json=model_entry,
        )
        if isinstance(result, dict) and result.get("ok") is False:
            raise RuntimeError(result.get("error") or "边缘 Agent 热更新失败")
        return result if isinstance(result, dict) else {}

    @classmethod
    async def _dispatch_algorithm_model(cls, algorithm: AlgorithmModel, auth: AuthSchema) -> dict:
        """枚举引用任务并逐任务下发；单任务失败被捕获，不影响其余任务。"""
        tasks = await cls._list_referencing_tasks(algorithm.id)
        return await cls._dispatch_tasks(tasks, algorithm)

    @classmethod
    async def _dispatch_tasks(cls, tasks: list[AlgorithmTaskModel], algorithm: AlgorithmModel) -> dict:
        """对指定任务集合逐条下发模型热更新，汇总 `{succeeded, failed}`。"""
        succeeded: list[int] = []
        failed: list[dict] = []
        for task in tasks:
            try:
                await cls._dispatch_task_model_update(task, algorithm)
                succeeded.append(task.id)
            except Exception as e:  # noqa: BLE001 - 单任务失败隔离，汇总返回由调用方重试
                logger.warning(f"[模型热更新] 下发失败: algorithm_id={algorithm.id} task_id={task.id} {e}")
                failed.append({"task_id": task.id, "error": _error_text(e)})
        if failed:
            # 部分失败必须可观测：ERROR 级 + 明确的任务清单，供运维重试
            logger.error(
                f"[模型热更新] algorithm_id={algorithm.id} 下发存在失败："
                f"成功 {succeeded} / 失败 {[f['task_id'] for f in failed]}；"
                "可重新执行热更新或调用回滚下发重试接口"
            )
        return {"succeeded": succeeded, "failed": failed}

    @classmethod
    async def hot_update_service(cls, id: int, auth: AuthSchema) -> dict:
        """把当前模型热更新下发到所有引用任务。

        `previous_*` 已在算法更新路径（`update_algorithm_service`）于模型真正变更时记录，
        本接口**不再改写** `previous_*`；若尚未发生变更则保持为空。
        """
        algorithm = await cls._load_algorithm(id, auth)
        if not algorithm:
            raise CustomException(msg="算法不存在", code=404, status_code=404)

        # 枚举引用任务并逐任务下发，部分失败不整体回滚
        result = await cls._dispatch_algorithm_model(algorithm, auth)
        logger.info(
            f"[模型热更新] algorithm_id={id} succeeded={len(result['succeeded'])} failed={len(result['failed'])}"
        )
        return result

    @classmethod
    async def rollback_service(cls, id: int, auth: AuthSchema) -> dict:
        """把当前模型与 previous_* 交换，并按恢复后的旧模型重新下发。"""
        algorithm = await cls._load_algorithm(id, auth)
        if not algorithm:
            raise CustomException(msg="算法不存在", code=404, status_code=404)
        if not algorithm.previous_model_path and not algorithm.previous_version:
            raise CustomException(msg="无可回滚的模型版本", code=400, status_code=400)

        prev_path = algorithm.previous_model_path
        prev_version = algorithm.previous_version
        cur_path = algorithm.model_path
        cur_version = algorithm.version

        # 交换：当前值退位为 previous_*，previous_* 恢复为当前值
        new_version = prev_version or cur_version
        await cls._persist_algorithm_fields(
            id,
            {
                "model_path": prev_path,
                "version": new_version,
                "previous_model_path": cur_path,
                "previous_version": cur_version,
            },
            auth,
        )
        algorithm.model_path = prev_path
        algorithm.version = new_version
        algorithm.previous_model_path = cur_path
        algorithm.previous_version = cur_version

        result = await cls._dispatch_algorithm_model(algorithm, auth)
        logger.info(
            f"[模型回滚] algorithm_id={id} succeeded={len(result['succeeded'])} failed={len(result['failed'])}"
        )
        if result["failed"] and not result["succeeded"]:
            # 补偿：全部任务下发失败时 DB 已交换但 Agent 仍用旧模型，属静默不一致。
            # 这里把 DB 交换还原（当前值退回 current），并抛出可操作错误，避免状态分裂。
            await cls._persist_algorithm_fields(
                id,
                {
                    "model_path": cur_path,
                    "version": cur_version,
                    "previous_model_path": prev_path,
                    "previous_version": prev_version,
                },
                auth,
            )
            failed_ids = [f["task_id"] for f in result["failed"]]
            logger.error(
                f"[模型回滚] algorithm_id={id} 全部任务下发失败，已还原模型配置；失败任务：{failed_ids}"
            )
            raise CustomException(
                msg=f"回滚下发全部失败，已还原原模型配置；失败任务：{failed_ids}",
                code=502,
                status_code=502,
            )
        return result

    @classmethod
    async def retry_dispatch_service(cls, id: int, task_ids: list[int], auth: AuthSchema) -> dict:
        """重试向指定任务下发当前模型（补偿部分失败的热更新/回滚）。"""
        algorithm = await cls._load_algorithm(id, auth)
        if not algorithm:
            raise CustomException(msg="算法不存在", code=404, status_code=404)
        wanted = {int(t) for t in (task_ids or [])}
        all_tasks = await cls._list_referencing_tasks(algorithm.id)
        tasks = [t for t in all_tasks if t.id in wanted]
        if not tasks:
            raise CustomException(msg="未找到可重试的任务", code=400, status_code=400)
        result = await cls._dispatch_tasks(tasks, algorithm)
        logger.info(
            f"[模型热更新] 重试下发 algorithm_id={id} tasks={sorted(wanted)} "
            f"succeeded={len(result['succeeded'])} failed={len(result['failed'])}"
        )
        return result
