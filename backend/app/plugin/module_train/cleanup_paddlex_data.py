"""一次性清理 paddlex 框架的历史测试数据（框架已下线）。

策略：
1. 删除 5 张业务表中的 framework='paddlex' 行（历史 schema 中 train_evals.framework
   为 varchar、其余为 enum，统一用原生 SQL 以兼容两种类型）；
2. 删除 framework='paddlex' 的模型仓库；
3. 删除已无任何版本（唯一版本来自 paddlex 且已被删除）的孤儿仓库；
4. 将 latest_version_id 指向已删除版本的仓库的 latest_version_id 置空。
"""
import asyncio

from sqlalchemy import text

from app.api.v1.module_system.user.model import (
    UserModel,  # noqa: F401  # 注册 mapper，避免关系解析失败
)
from app.core.database import async_db_session

_TABLES = (
    "train_models",
    "train_tasks",
    "train_evals",
    "train_predicts",
    "train_deploys",
)


async def main() -> None:
    async with async_db_session.begin() as db:
        counts = {}
        for table in _TABLES:
            result = await db.execute(text(f"DELETE FROM {table} WHERE framework = 'PADDLEX'"))
            counts[table] = result.rowcount
        print(f"deleted paddlex rows: {counts}")

        repo_paddlex = await db.execute(text("DELETE FROM train_model_repos WHERE framework = 'PADDLEX'"))
        print(f"deleted paddlex repos: {repo_paddlex.rowcount}")

        orphan_ids = (await db.execute(text(
            "SELECT id FROM train_model_repos "
            "WHERE id NOT IN (SELECT DISTINCT repo_id FROM train_models WHERE repo_id IS NOT NULL)"
        ))).scalars().all()
        if orphan_ids:
            await db.execute(text(
                "DELETE FROM train_model_repos WHERE id = ANY(:ids)"
            ).bindparams(ids=orphan_ids))
        print(f"deleted orphan repos (0 remaining versions): {len(orphan_ids)}")

        dangling_ids = (await db.execute(text(
            "SELECT id FROM train_model_repos "
            "WHERE latest_version_id IS NOT NULL "
            "AND latest_version_id NOT IN (SELECT id FROM train_models)"
        ))).scalars().all()
        if dangling_ids:
            await db.execute(text(
                "UPDATE train_model_repos SET latest_version_id = NULL WHERE id = ANY(:ids)"
            ).bindparams(ids=dangling_ids))
        print(f"nulled dangling latest_version_id on repos: {len(dangling_ids)}")


if __name__ == "__main__":
    asyncio.run(main())
