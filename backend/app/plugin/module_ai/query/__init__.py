"""问数插件包。

⚠️ **先导入 service**（顺序敏感，别删）：
``service`` 在模块顶层按名字从各子模块取符号（``from .metric_rules import AGG_INTENT``、
``from .execution import _execute_sql``……），而子模块顶层又 ``from . import service``。
若调用方先导入某个子模块（如 ``from .query.metric_rules import ...``），两边会互相等待，
报 ``partially initialized module`` ImportError（实测 metric_rules / sqlguard / sqlcache /
execution / runtime_flags / datasource_core / metrics_ops 都会踩）。

包初始化先完整加载 service，之后任何子模块入口都是安全的。
"""
from . import service  # noqa: F401  （顺序敏感：必须在本包任何其它子模块之前）

__all__ = ["service"]
