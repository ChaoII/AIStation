import os
import re
import tempfile

from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError

from app.core.database import async_db_session
from app.core.logger import log

from .model import TrainDeploy, TrainEval, TrainModel, TrainPredict, TrainTask

_EPOCH_RE = re.compile(r"^\s*(\d+)/(\d+)\s+")
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text).replace("\r", "")


def _calc_progress_from_log(task_id: int) -> int | None:
    log_path = os.path.join(tempfile.gettempdir(), "train_output", str(task_id), "train.log")
    if not os.path.isfile(log_path):
        return None
    try:
        with open(log_path, "rb") as f:
            size = f.seek(0, 2)
            if size == 0:
                return None
            tail_size = min(size, 16384)
            f.seek(-tail_size, 2)
            chunk = f.read(tail_size).decode("utf-8", errors="replace")
        epoch = total = 0
        for line in chunk.splitlines():
            clean = _strip_ansi(line)
            m = _EPOCH_RE.search(clean)
            if m:
                e = int(m.group(1))
                t = int(m.group(2))
                if e > epoch:
                    epoch, total = e, t
        if total > 0:
            return int(epoch / total * 100)
    except Exception as e:
        log.warning(f"[train-progress-log] exception: {e}")
    return None


def _model_to_dict(row) -> dict:
    cols = {}
    for c in row.__table__.columns:
        try:
            cols[c.name] = getattr(row, c.name)
        except Exception:
            pass
    for k in ("_sa_instance_state",):
        cols.pop(k, None)
    return cols


def _enrich_task(row) -> dict:
    d = _model_to_dict(row)
    if d.get("status") == "running":
        live = _calc_progress_from_log(d.get("id", 0))
        if live is not None:
            d["progress"] = live
    return d


class TrainService:

    @classmethod
    async def list_models(cls, params: dict | None = None) -> tuple[list[dict], int]:
        page_no = max(1, int((params or {}).get("page_no", 1)))
        page_size = max(1, min(100, int((params or {}).get("page_size", 20))))
        name = (params or {}).get("name")
        framework = (params or {}).get("framework")

        async with async_db_session() as db:
            stmt = select(TrainModel)
            if name:
                stmt = stmt.where(TrainModel.name.ilike(f"%{name}%"))
            if framework:
                stmt = stmt.where(TrainModel.framework == framework)
            count_stmt = select(func.count()).select_from(stmt.subquery())
            total = (await db.execute(count_stmt)).scalar() or 0
            stmt = stmt.order_by(desc(TrainModel.created_time)).limit(page_size).offset((page_no - 1) * page_size)
            result = await db.execute(stmt)
            rows = result.scalars().all()
            return [_model_to_dict(r) for r in rows], total

    @classmethod
    async def get_model(cls, model_id: int) -> dict | None:
        async with async_db_session() as db:
            m = await db.get(TrainModel, model_id)
            return _model_to_dict(m) if m else None

    @classmethod
    async def update_model(cls, model_id: int, data: dict) -> dict | None:
        async with async_db_session.begin() as db:
            m = await db.get(TrainModel, model_id)
            if not m:
                return None
            for key, val in data.items():
                if hasattr(m, key) and val is not None:
                    setattr(m, key, val)
            return {"id": m.id}

    @classmethod
    async def create_model(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            existing = await db.execute(
                select(TrainModel).where(TrainModel.name == data.name).order_by(desc(TrainModel.id)).limit(1)
            )
            last = existing.scalar_one_or_none()
            next_ver = 1
            if last and last.version:
                try:
                    next_ver = int(last.version.replace("v", "")) + 1
                except ValueError:
                    next_ver = 1
            for _ in range(3):
                version = f"v{next_ver}"
                m = TrainModel(
                    name=data.name, framework=data.framework,
                    version=version, annotation_dataset_id=data.annotation_dataset_id,
                    export_format=data.export_format, description=data.description,
                    created_id=auth.user.id,
                )
                db.add(m)
                try:
                    await db.flush()
                    return {"id": m.id, "version": version}
                except IntegrityError:
                    await db.rollback()
                    next_ver += 1
            raise Exception("版本冲突，请重试")

    @classmethod
    async def delete_models(cls, ids: list[int]) -> None:
        async with async_db_session.begin() as db:
            for mid in ids:
                m = await db.get(TrainModel, mid)
                if m:
                    await db.delete(m)

    @classmethod
    async def list_tasks(cls, params: dict | None = None) -> tuple[list[dict], int]:
        page_no = max(1, int((params or {}).get("page_no", 1)))
        page_size = max(1, min(100, int((params or {}).get("page_size", 20))))
        name = (params or {}).get("name")
        framework = (params or {}).get("framework")
        status = (params or {}).get("status")

        async with async_db_session() as db:
            stmt = select(TrainTask)
            if name:
                stmt = stmt.where(TrainTask.name.ilike(f"%{name}%"))
            if framework:
                stmt = stmt.where(TrainTask.framework == framework)
            if status:
                stmt = stmt.where(TrainTask.status == status)
            count_stmt = select(func.count()).select_from(stmt.subquery())
            total = (await db.execute(count_stmt)).scalar() or 0
            stmt = stmt.order_by(desc(TrainTask.created_time)).limit(page_size).offset((page_no - 1) * page_size)
            result = await db.execute(stmt)
            rows = result.scalars().all()
            return [_enrich_task(r) for r in rows], total

    @classmethod
    async def get_task(cls, task_id: int) -> dict | None:
        async with async_db_session() as db:
            t = await db.get(TrainTask, task_id)
            return _enrich_task(t) if t else None

    @classmethod
    async def create_task(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            image = "paddlecloud/paddlex:3.0" if data.framework == "paddlex" else "ultralytics/ultralytics:latest"
            t = TrainTask(
                name=data.name, framework=data.framework, dataset_id=data.dataset_id,
                annotation_task_id=data.annotation_task_id,
                base_model_id=data.base_model_id, docker_image=image,
                hyperparams=data.hyperparams, created_id=auth.user.id,
            )
            db.add(t)
            await db.flush()
            return {"id": t.id}

    @classmethod
    async def delete_tasks(cls, ids: list[int]) -> None:
        async with async_db_session.begin() as db:
            for tid in ids:
                t = await db.get(TrainTask, tid)
                if t:
                    await db.delete(t)

    @classmethod
    async def stop_task(cls, task_id: int) -> dict:
        from .scheduler import stop_training
        await stop_training(task_id)
        return {"id": task_id}

    @classmethod
    async def create_eval(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            e = TrainEval(
                model_repo_id=data.model_repo_id,
                model_id=data.model_id,
                eval_dataset_id=data.eval_dataset_id,
                hyperparams=data.hyperparams,
                created_id=auth.user.id,
            )
            db.add(e)
            await db.flush()
            return {"id": e.id}

    @classmethod
    async def list_evals(cls, params: dict | None = None) -> tuple[list[dict], int]:
        page_no = max(1, int((params or {}).get("page_no", 1)))
        page_size = max(1, min(100, int((params or {}).get("page_size", 20))))
        model_repo_id = (params or {}).get("model_repo_id")
        name = (params or {}).get("name")
        framework = (params or {}).get("framework")
        status = (params or {}).get("status")

        async with async_db_session() as db:
            stmt = select(TrainEval)
            if model_repo_id:
                stmt = stmt.where(TrainEval.model_repo_id == int(model_repo_id))
            if name:
                from .model import TrainModel as TM
                matched_model_ids = (
                    await db.execute(select(TM.id).where(TM.name.ilike(f"%{name}%")))
                ).scalars().all()
                if matched_model_ids:
                    stmt = stmt.where(TrainEval.model_id.in_(matched_model_ids))
                else:
                    stmt = stmt.where(TrainEval.model_id == -1)
            if framework:
                stmt = stmt.where(TrainEval.framework == framework)
            if status:
                stmt = stmt.where(TrainEval.status == status)
            count_stmt = select(func.count()).select_from(stmt.subquery())
            total = (await db.execute(count_stmt)).scalar() or 0
            stmt = stmt.order_by(desc(TrainEval.created_time)).limit(page_size).offset((page_no - 1) * page_size)
            result = await db.execute(stmt)
            rows = result.scalars().all()
            return [_model_to_dict(r) for r in rows], total

    @classmethod
    async def delete_evals(cls, ids: list[int]) -> None:
        async with async_db_session.begin() as db:
            for eid in ids:
                e = await db.get(TrainEval, eid)
                if e:
                    await db.delete(e)

    @classmethod
    async def get_eval(cls, eval_id: int) -> dict | None:
        import os
        import tempfile

        async with async_db_session() as db:
            e = await db.get(TrainEval, eval_id)
            if not e:
                return None
            data = _model_to_dict(e)

            log_path = os.path.join(tempfile.gettempdir(), "eval_output", str(eval_id), "eval.log")
            if os.path.exists(log_path):
                try:
                    with open(log_path, encoding="utf-8", errors="replace") as f:
                        data["log"] = f.read()[-500000:]
                except Exception:
                    pass
            return data

    @classmethod
    async def create_predict(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            p = TrainPredict(
                model_repo_id=data.model_repo_id,
                model_id=data.model_id,
                source_type=data.source_type,
                source_dataset_id=data.source_dataset_id,
                source_images=data.source_images,
                hyperparams=data.hyperparams,
                created_id=auth.user.id,
            )
            db.add(p)
            await db.flush()
            return {"id": p.id}

    @classmethod
    async def get_predict(cls, predict_id: int) -> dict | None:
        import os
        import tempfile

        async with async_db_session() as db:
            p = await db.get(TrainPredict, predict_id)
            if not p:
                return None
            data = _model_to_dict(p)

            log_path = os.path.join(tempfile.gettempdir(), "predict_output", str(predict_id), "predict.log")
            if os.path.exists(log_path):
                try:
                    with open(log_path, encoding="utf-8", errors="replace") as f:
                        data["log"] = f.read()[-500000:]
                except Exception:
                    pass
            return data

    @classmethod
    async def list_predicts(cls, params: dict | None = None) -> tuple[list[dict], int]:
        page_no = max(1, int((params or {}).get("page_no", 1)))
        page_size = max(1, min(100, int((params or {}).get("page_size", 20))))
        status = (params or {}).get("status")
        name = (params or {}).get("name")

        async with async_db_session() as db:
            stmt = select(TrainPredict)
            if status:
                stmt = stmt.where(TrainPredict.status == status)
            if name:
                from .model import TrainModel as TM
                matched_model_ids = (
                    await db.execute(select(TM.id).where(TM.name.ilike(f"%{name}%")))
                ).scalars().all()
                if matched_model_ids:
                    stmt = stmt.where(TrainPredict.model_id.in_(matched_model_ids))
                else:
                    stmt = stmt.where(TrainPredict.model_id == -1)
            count_stmt = select(func.count()).select_from(stmt.subquery())
            total = (await db.execute(count_stmt)).scalar() or 0
            stmt = stmt.order_by(desc(TrainPredict.created_time)).limit(page_size).offset((page_no - 1) * page_size)
            result = await db.execute(stmt)
            rows = result.scalars().all()
            return [_model_to_dict(r) for r in rows], total

    @classmethod
    async def delete_predicts(cls, ids: list[int]) -> None:
        async with async_db_session.begin() as db:
            for pid in ids:
                p = await db.get(TrainPredict, pid)
                if p:
                    await db.delete(p)

    @classmethod
    async def upload_predict_images(cls, files: list, auth) -> list[str]:
        import io
        import uuid

        from app.utils.s3_client import s3_client

        keys = []
        for f in files:
            content = await f.read()
            ext = f.filename.rsplit(".", 1)[-1] if "." in f.filename else "jpg"
            key = f"train/predict/upload/{auth.user.id}/{uuid.uuid4()}.{ext}"
            s3_client.upload_fileobj(io.BytesIO(content), key)
            keys.append(key)
        return keys

    @classmethod
    async def export_dataset(cls, data, auth) -> dict:
        import os
        import shutil
        import tempfile
        import zipfile

        from .exporter import export_dataset_for_download as run_export

        # If annotation_task_id is set, check the task is completed
        if data.annotation_task_id:
            from app.api.v1.module_annotation.task.model import AnnotationTaskModel
            from app.api.v1.module_annotation.task.service import TaskService
            from app.core.database import async_db_session
            async with async_db_session() as db:
                ann_task = await db.get(AnnotationTaskModel, data.annotation_task_id)
                if not ann_task:
                    raise Exception("标注任务不存在")
                # Recalculate actual progress before checking
                try:
                    prog = await TaskService._calc_progress(db, ann_task.id, ann_task.dataset_id)
                except Exception:
                    prog = {"status": "pending"}
                status = prog.get("status", "pending")
                if status != "completed":
                    raise Exception(f"标注任务「{ann_task.name}」尚未完成，请先完成标注再导出")

        export_dir = os.path.join(tempfile.gettempdir(), "dataset_export", str(data.dataset_id), data.format)
        if os.path.exists(export_dir):
            shutil.rmtree(export_dir)
        os.makedirs(export_dir, exist_ok=True)

        await run_export(data.dataset_id, data.annotation_task_id or 0, data.format, export_dir, annotation_task_id=data.annotation_task_id, ocr_rec=data.ocr_rec, train_ratio=data.train_ratio)

        # Zip with top-level directory matching zip name
        zip_name = f"dataset_{data.dataset_id}_{data.format}"
        zip_dir = os.path.join(os.path.dirname(export_dir), zip_name)
        if os.path.exists(zip_dir):
            shutil.rmtree(zip_dir)
        shutil.move(export_dir, zip_dir)
        zip_path = zip_dir + ".zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(zip_dir):
                for fn in files:
                    fp = os.path.join(root, fn)
                    zf.write(fp, os.path.relpath(fp, os.path.dirname(zip_dir)))
        shutil.rmtree(zip_dir, ignore_errors=True)

        # Upload to RustFS
        rustfs_key = f"train/exports/dataset_{data.dataset_id}_{data.format}_{auth.user.id}.zip"
        from app.utils.s3_client import s3_client
        with open(zip_path, "rb") as f:
            s3_client.upload_fileobj(f, rustfs_key)

        download_url = s3_client.presigned_url(rustfs_key)
        shutil.rmtree(os.path.dirname(export_dir), ignore_errors=True)

        # Schedule cleanup after presigned URL expires
        import asyncio

        from app.config.setting import settings
        expiry_secs = settings.RUSTFS_PRESIGNED_URL_EXPIRY

        async def _delayed_cleanup():
            await asyncio.sleep(expiry_secs + 60)
            try:
                s3_client.delete_object(rustfs_key)
            except Exception:
                pass
        asyncio.create_task(_delayed_cleanup())

        return {"download_url": download_url, "format": data.format, "dataset_id": data.dataset_id}

    @classmethod
    async def create_deploy(cls, data, auth) -> dict:
        import uuid
        async with async_db_session.begin() as db:
            model_rec = await db.get(TrainModel, data.model_id)
            if not model_rec:
                raise Exception("模型不存在")
            d = TrainDeploy(
                name=data.name or f"{model_rec.name} v{model_rec.version}",
                model_id=data.model_id,
                model_name=model_rec.name,
                model_version=model_rec.version,
                framework=model_rec.framework,
                device=data.device,
                host_port=data.host_port or 0,
                api_key=uuid.uuid4().hex,
                hyperparams=data.hyperparams,
                created_id=auth.user.id,
            )
            db.add(d)
            await db.flush()
            return TrainService._deploy_to_dict(d)

    @classmethod
    def _deploy_to_dict(cls, row) -> dict:
        return {c.name: getattr(row, c.name) for c in row.__table__.columns if hasattr(row, c.name)}

    @classmethod
    async def list_deploys(cls, params: dict | None = None) -> tuple[list[dict], int]:
        page_no = max(1, int((params or {}).get("page_no", 1)))
        page_size = max(1, min(100, int((params or {}).get("page_size", 20))))
        status = (params or {}).get("status")
        name = (params or {}).get("name")

        async with async_db_session() as db:
            stmt = select(TrainDeploy).order_by(desc(TrainDeploy.created_time))
            if status:
                stmt = stmt.where(TrainDeploy.status == status)
            if name:
                stmt = stmt.where(TrainDeploy.name.ilike(f"%{name}%"))
            count_stmt = select(func.count()).select_from(stmt.subquery())
            total = (await db.execute(count_stmt)).scalar() or 0
            stmt = stmt.limit(page_size).offset((page_no - 1) * page_size)
            result = await db.execute(stmt)
            return [_model_to_dict(r) for r in result.scalars().all()], total

    @classmethod
    async def get_deploy(cls, deploy_id: int) -> dict | None:
        async with async_db_session() as db:
            d = await db.get(TrainDeploy, deploy_id)
            return _model_to_dict(d) if d else None

    @classmethod
    async def delete_deploys(cls, ids: list[int]) -> None:
        async with async_db_session.begin() as db:
            for did in ids:
                d = await db.get(TrainDeploy, did)
                if d:
                    if d.container_id:
                        from .deploy_executor import stop_deployment
                        await stop_deployment(d.id)
                    await db.delete(d)

    @classmethod
    async def renew_deploy_key(cls, deploy_id: int) -> dict | None:
        import uuid
        async with async_db_session.begin() as db:
            d = await db.get(TrainDeploy, deploy_id)
            if not d:
                return None
            new_key = uuid.uuid4().hex
            d.api_key = new_key
            return {"api_key": new_key, "id": d.id}
