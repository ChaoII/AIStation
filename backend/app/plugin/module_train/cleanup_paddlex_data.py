"""一次性清理 paddlex 框架的历史测试数据（框架已下线）。"""
import asyncio

from sqlalchemy import delete

from app.core.database import async_db_session

from .model import TrainDeploy, TrainEval, TrainModel, TrainPredict, TrainTask


async def main() -> None:
    async with async_db_session.begin() as db:
        counts = {}
        for model in (TrainModel, TrainTask, TrainEval, TrainPredict, TrainDeploy):
            result = await db.execute(
                delete(model).where(model.framework == "paddlex")
            )
            counts[model.__tablename__] = result.rowcount
        print(f"deleted paddlex rows: {counts}")


if __name__ == "__main__":
    asyncio.run(main())
