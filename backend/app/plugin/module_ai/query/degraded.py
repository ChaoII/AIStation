"""静默降级计数：哪些能力「坏了但流程还在跑」。

从 ``service.py`` 拆出（2026-11-08）。问数链路有近 30 处容错 ``except``，容错本身是
对的（一个附加统计失败不该让整页 500），但这些失败**不留任何痕迹**。实测三次事故
都是这么来的：影子表没建出来（no such table）、启动对账没生效、资产血缘恒为 0 ——
界面结构正常、数字全空，没人会发现。

约定：``except`` 里不再写裸 ``pass``，改 ``degrade("能力名", e)`` ——
计数 + 首次几次打日志 + 暴露到 ``GET /ai/query/system/degraded``。

``service.py`` 保留 ``_degrade`` / ``degraded_status`` / ``reset_degraded`` 三个旧名字
的再导出，调用点（含测试里的 monkeypatch）零改动。
"""
from __future__ import annotations

import time
from collections import Counter

from app.core.logger import log

#: 每个能力最多打几次 warning（避免每次请求刷屏）
DEGRADE_LOG_TIMES = 3

#: 降级计数与最后一次错误信息（进程级单例；``reset_degraded()`` 会清空）
_DEGRADED: Counter[str] = Counter()
_DEGRADED_INFO: dict[str, dict] = {}


def degrade(area: str, exc: BaseException | None = None) -> None:
    """记录一次静默降级（能力不可用，流程继续）。"""
    _DEGRADED[area] += 1
    _DEGRADED_INFO[area] = {
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "error": f"{type(exc).__name__}: {exc}"[:200] if exc else "",
    }
    if _DEGRADED[area] <= DEGRADE_LOG_TIMES:
        log.warning(
            "[query][降级] {}: {}",
            area,
            f"{type(exc).__name__}: {exc}"[:160] if exc else "(无异常信息)",
        )


def degraded_status() -> dict:
    """降级状态快照（给健康检查 / 运维看：现在有哪些能力是坏的）。"""
    return {
        "total": sum(_DEGRADED.values()),
        "areas": [
            {"area": k, "count": v, **(_DEGRADED_INFO.get(k) or {})}
            for k, v in _DEGRADED.most_common()
        ],
    }


def reset_degraded() -> None:
    """清空计数（测试与人工排查用）。"""
    _DEGRADED.clear()
    _DEGRADED_INFO.clear()
