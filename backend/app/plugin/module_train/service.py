from sqlalchemy import select, desc
from app.core.database import async_db_session
from .model import TrainModel, TrainTask, TrainEval


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
                created_id=auth.user.id,
            )
            db.add(m)
            await db.flush()
            return {"id": m.id, "version": version}

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
                base_model_id=data.base_model_id, docker_image=image,
                hyperparams=data.hyperparams, created_id=auth.user.id,
            )
            db.add(t)
            await db.flush()
            return {"id": t.id}

    @classmethod
    async def stop_task(cls, task_id: int) -> dict:
        from .scheduler import stop_training
        await stop_training(task_id)
        return {"id": task_id}

    @classmethod
    async def create_eval(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            e = TrainEval(model_repo_id=data.model_repo_id, eval_dataset_id=data.eval_dataset_id, created_id=auth.user.id)
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
