"""问数权限模型（统一策略引擎的数据层）。

子包职责划分（后续任务逐步补齐）：

- ``model.py``（本文件）：三张表的 DDL 常量 + 幂等建表 + 敏感表清单查询；
- 判定引擎、SQL 编译器、迁移器（backfill）与审计写入都建在这三张表之上。

为什么不用 alembic autogenerate：本项目的问数侧影子表一直是**启动期幂等建表**
（见 ``service._ensure_query_tables``），插件表也不在迁移链里；走 autogenerate 会把
dev 库 400+ 张未被模型覆盖的历史表判成待 DROP（灾难级）。
"""
