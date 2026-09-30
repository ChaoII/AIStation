"""训练指标：主指标选择与最优轮次。

TorchKiln 的"最优"由它自己在配置里声明的 ``main_indicator`` 决定（如
``mAP50-95`` / ``hmean`` / ``acc``），解析出来的指标键名随任务而变，所以这里
按"候选键里第一个有值的"来挑，而不是像以前那样给 ultralytics / PaddleX 各写
一张映射表——那两个框架已退场，表也一并没了。

前端统一从 ``best_metrics`` 读取主指标，避免各执行器内联策略分裂。
"""

#: 主指标候选键，按优先级排列（TorchKiln 各任务的 main_indicator 都在其中）。
#: 顺序即优先级：越靠前越"权威"。``map50`` 系列放在前面是因为检测类任务最常见，
#: 且它比泛化的 ``acc`` 更能反映检测质量。
_PRIMARY_CANDIDATES: tuple[str, ...] = (
    "mAP50-95", "mAP50", "map50_95", "map50",
    "hmean", "top1", "acc", "accuracy", "f1",
)


def primary_metric_key(framework: str, task_type: str = "", mode: str | None = None) -> str:
    """返回该框架/任务的主指标键。

    ⚠️ 这个返回值现在只是**首选键**而非唯一键——真实指标名由 TorchKiln 配置的
    ``main_indicator`` 决定，:func:`best_metric` 会在 ``_PRIMARY_CANDIDATES``
    里依次探测，取第一个有值的。保留这个函数是为了让调用方（以及前端展示
    "主指标"标签）有个稳定的默认键。

    ``framework`` / ``task_type`` / ``mode`` 三个参数保留签名：调用点不必为
    退场再改一轮，而 TorchKiln 的任务类型将来若要细分优先级也能用得上。
    """
    return _PRIMARY_CANDIDATES[0]


def best_metric(
    metrics_log: list[dict] | None,
    framework: str = "",
    task_type: str = "",
    mode: str | None = None,
) -> dict | None:
    """选出最优轮次。

    - 跳过 ``best: True`` 的汇总行（那是最终结果，不是某一轮的指标）
    - 按主指标候选键依次探测，取第一个有值的键，再在该键上取最大的一轮
    - 所有候选键都缺失时退最近一轮
    - 空列表返回 ``None``
    """
    rows = [m for m in (metrics_log or []) if isinstance(m, dict) and not m.get("best")]
    if not rows:
        return None
    for key in _PRIMARY_CANDIDATES:
        scored = [m for m in rows if m.get(key) is not None]
        if scored:
            return max(scored, key=lambda m: m.get(key, 0))
    return rows[-1]
