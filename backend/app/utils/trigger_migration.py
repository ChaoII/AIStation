"""旧 cron 列 → 统一 `trigger` / `trigger_args` 的**迁移专用**助手（A6）。

与写入路径的区别（规格 §4.4，**不做静默语义改写**）：

- 5 段标准 crontab → 原样规范化（周字段映射为星期名列表，与写入口径完全一致）；
- `?` → `*`（Quartz 专有语法**仅在读旧数据/迁移时容错**，写入接口一律拒绝）；
- 6 段且秒位为 `0` → 去掉首段后按 5 段规范化；
- 7 段且末段（年份）为 `*` / `?` → 等价于「无年份」，去掉该段后按 6 段处理
  （Quartz 默认会写 `0 0 9 * * ? *` 这种"年份通配"形式，语义上就是 5 段 cron）；
- **6 段秒位非 `0`、7 段带具体年份 → 跳过**（返回中文原因，由迁移日志逐条记录、人工确认）；
- 空值与解析失败的 5 段 → 跳过（同样记日志），不猜语义。

规范化的唯一实现是 :class:`~app.utils.trigger_util.TriggerUtil`——本模块**只做段数裁剪与 `?` 容错**，
绝不复制周字段映射表（口径唯一）。
"""

from __future__ import annotations

from app.utils.trigger_util import TriggerUtil

__all__ = ["normalize_legacy"]


def normalize_legacy(value) -> tuple[str, str | None, str | None]:
    """把旧 cron 列的值转为统一契约，返回 `(trigger, trigger_args, skip_reason)`。

    - 可等值转换：`("cron", "<规范化后的 5 段>", None)`；
    - 不可转换：`("cron", None, "<中文原因>")`——调用方**必须**把原因写进迁移日志，
      该行 `trigger_args` 保持为空，由列表接口标为「表达式需人工确认」（不能悄悄不跑）。
    """
    text = "" if value is None else str(value).strip()
    if not text:
        return "cron", None, "cron 表达式为空，跳过待人工确认"

    fields = text.split()
    count = len(fields)
    if count == 7:
        if fields[-1] not in ("*", "?"):
            return "cron", None, f"7 段（带年份）表达式不受支持，跳过待人工确认：{text}"
        # 年份通配（`*` / `?`）与「无年份」等价：裁掉该段后按 6 段处理
        fields = fields[:6]
        count = 6
    if count == 6:
        # 秒位判定复用统一层（唯一口径）：该方法在 TriggerUtil 内为私有，
        # 但语义与写入路径完全一致，这里刻意不另写一份，避免又出现"两套口径"
        if not TriggerUtil._is_zero(fields[0]):
            return (
                "cron",
                None,
                f"6 段表达式秒位非 0（秒级需求请改用 interval），跳过待人工确认：{text}",
            )
        fields = fields[1:]
        count = 5
    if count != 5:
        return "cron", None, f"段数不为 5（{count} 段），跳过待人工确认：{text}"

    # `?` → `*`：仅迁移路径容错（写入接口仍拒绝 Quartz 专有语法）
    expr = " ".join(fields).replace("?", "*")
    try:
        return "cron", TriggerUtil.normalize_cron(expr), None
    except ValueError as exc:
        return "cron", None, f"cron 表达式无法规范化（{exc}），跳过待人工确认：{text}"
