from sqlalchemy import select, desc
from app.core.database import async_db_session
from .model import TrainModel, TrainTask, TrainEval, TrainPredict


class TrainService:

    @classmethod
    async def list_models(cls) -> list[dict]:
        async with async_db_session() as db:
            result = await db.execute(select(TrainModel).order_by(desc(TrainModel.created_time)))
            rows = result.scalars().all()
            return [dict(r.__dict__) for r in rows]

    @classmethod
    async def get_model(cls, model_id: int) -> dict | None:
        async with async_db_session() as db:
            m = await db.get(TrainModel, model_id)
            return dict(m.__dict__) if m else None

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
            version = f"v{next_ver}"
            m = TrainModel(
                name=data.name, framework=data.framework,
                version=version, annotation_dataset_id=data.annotation_dataset_id,
                export_format=data.export_format,
                created_id=auth.user.id,
            )
            db.add(m)
            await db.flush()
            return {"id": m.id, "version": version}

    @classmethod
    async def delete_models(cls, ids: list[int]) -> None:
        async with async_db_session.begin() as db:
            for mid in ids:
                m = await db.get(TrainModel, mid)
                if m:
                    await db.delete(m)

    @classmethod
    async def list_tasks(cls) -> list[dict]:
        async with async_db_session() as db:
            result = await db.execute(select(TrainTask).order_by(desc(TrainTask.created_time)))
            return [dict(r.__dict__) for r in result.scalars().all()]

    @classmethod
    async def get_task(cls, task_id: int) -> dict | None:
        async with async_db_session() as db:
            t = await db.get(TrainTask, task_id)
            return dict(t.__dict__) if t else None

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
    async def list_evals(cls, model_repo_id: int) -> list[dict]:
        async with async_db_session() as db:
            result = await db.execute(
                select(TrainEval).where(TrainEval.model_repo_id == model_repo_id).order_by(desc(TrainEval.created_time))
            )
            return [dict(r.__dict__) for r in result.scalars().all()]

    @classmethod
    async def delete_evals(cls, ids: list[int]) -> None:
        async with async_db_session.begin() as db:
            for eid in ids:
                e = await db.get(TrainEval, eid)
                if e:
                    await db.delete(e)

    @classmethod
    async def get_eval(cls, eval_id: int) -> dict | None:
        async with async_db_session() as db:
            e = await db.get(TrainEval, eval_id)
            return dict(e.__dict__) if e else None

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
        async with async_db_session() as db:
            p = await db.get(TrainPredict, predict_id)
            return dict(p.__dict__) if p else None

    @classmethod
    async def list_predicts(cls) -> list[dict]:
        async with async_db_session() as db:
            result = await db.execute(select(TrainPredict).order_by(desc(TrainPredict.created_time)))
            return [dict(r.__dict__) for r in result.scalars().all()]

    @classmethod
    async def delete_predicts(cls, ids: list[int]) -> None:
        async with async_db_session.begin() as db:
            for pid in ids:
                p = await db.get(TrainPredict, pid)
                if p:
                    await db.delete(p)

    @classmethod
    async def upload_predict_images(cls, files: list, auth) -> list[str]:
        import uuid
        import io
        import os
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
        import os, tempfile, shutil, zipfile
        from .exporter import export_dataset as run_export

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

        await run_export(data.dataset_id, data.annotation_task_id or 0, data.format, export_dir, annotation_task_id=data.annotation_task_id, ocr_rec=data.ocr_rec)

        # Zip the export
        zip_path = export_dir.rstrip("/") + ".zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(export_dir):
                for fn in files:
                    fp = os.path.join(root, fn)
                    zf.write(fp, os.path.relpath(fp, export_dir))

        # Upload to RustFS
        rustfs_key = f"train/exports/dataset_{data.dataset_id}_{data.format}_{auth.user.id}.zip"
        from app.utils.s3_client import s3_client
        with open(zip_path, "rb") as f:
            s3_client.upload_fileobj(f, rustfs_key)

        download_url = s3_client.presigned_url(rustfs_key)
        shutil.rmtree(os.path.dirname(export_dir), ignore_errors=True)

        return {"download_url": download_url, "format": data.format, "dataset_id": data.dataset_id}
