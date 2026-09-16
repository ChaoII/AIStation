"""训练指标：主指标选择与最优轮次。

不同框架/任务的"最优"判定标准不同：
- ultralytics 检测/分割/姿态/旋转框：mAP50（``map50``）
- ultralytics 分类：Top-1 准确率（``top1``）
- PaddleX OCR det：hmean；rec：acc（``acc``）

前端统一从 ``best_metrics`` 读取主指标，避免各执行器内联策略分裂。
"""

# 显式主指标映射（键为 (framework, task_type/mode) 组合的小写形式）
_PRIMARY = {
    ("ultralytics", "classification"): "top1",
    ("ultralytics", "cls"): "top1",
    ("paddlex", "rec"): "acc",
    ("paddlex", "det"): "hmean",
}


def primary_metric_key(framework: str, task_type: str, mode: str | None = None) -> str:
    """按框架/任务/模式返回主指标键。

    - ``paddlex``：``rec`` → ``acc``，其余（``det``）→ ``hmean``
    - ``ultralytics``：分类 → ``top1``，其余任务 → ``map50``
    - 其他/未知：回退 ``map50``
    """
    fw = (framework or "").lower()
    tt = (task_type or "").lower()
    if fw == "paddlex":
        return _PRIMARY.get(("paddlex", (mode or "det").lower()), "hmean")
    if fw == "ultralytics":
        return _PRIMARY.get(("ultralytics", tt), "map50")
    return "map50"


def best_metric(
    metrics_log: list[dict] | None,
    framework: str,
    task_type: str = "detection",
    mode: str | None = None,
) -> dict | None:
    """选出最优轮次。

    - 过滤掉 ``best: True`` 的汇总记录（PaddleX 会额外输出 best metric 行）
    - 按主指标取最大的一轮；主指标全部缺失时退最近一轮
    - 空列表返回 ``None``
    """
    rows = [m for m in (metrics_log or []) if isinstance(m, dict) and not m.get("best")]
    if not rows:
        return None
    key = primary_metric_key(framework, task_type, mode)
    scored = [m for m in rows if m.get(key) is not None]
    if scored:
        return max(scored, key=lambda m: m.get(key, 0))
    return rows[-1]
