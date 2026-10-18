"""慢路径耗时归因：到底慢在哪（不调模型，只解析日志）。

把每次提问拆成 生成(LLM) / 执行(SQL) / 收尾(检索+DQ) 三段，
并检验「prompt 长度」与「生成耗时」的相关性 —— 判断是 prompt 大还是网关慢。

用法：python scripts/_diag_latency.py <日志路径>
"""

from __future__ import annotations

import os
import re
import sys
from statistics import mean, median, pstdev

TS = r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)"


def pct(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    return s[min(len(s) - 1, int(len(s) * p))]


def main(path: str) -> None:
    raw = open(path, "rb").read()
    # ⚠️ PowerShell 的 Tee-Object 默认写 **UTF-16LE**（带 BOM），按 UTF-8 读会全是 \x00，
    #    导致子串匹配全部落空（实测踩过）。先看 BOM 再决定编码。
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        txt = raw.decode("utf-16", errors="replace")
    elif raw[:3] == b"\xef\xbb\xbf":
        txt = raw.decode("utf-8-sig", errors="replace")
    else:
        txt = raw.decode("utf-8", errors="replace")
    lines = txt.splitlines()

    recs: list[dict] = []
    last_prompt = 0
    last_schema_ms = 0
    last_agno_ms = 0
    agno_times: list[int] = []
    schema_times: list[int] = []
    for ln in lines:
        if "_nl2sql:" in ln:  # prompt 长度=N 字符（schema 构建=Mms）/ agno 阶段耗时=Mms
            nums_ms = [int(x) for x in re.findall(r"=(\d+)ms", ln)]
            if "agno" in ln.lower() or (nums_ms and "阶段耗时" in ln):
                if nums_ms:
                    last_agno_ms = nums_ms[0]
                    agno_times.append(nums_ms[0])
            else:
                m1 = re.findall(r"=(\d+)", ln)
                if m1:
                    last_prompt = int(m1[0])
                if nums_ms:
                    last_schema_ms = nums_ms[0]
                    schema_times.append(nums_ms[0])
                last_retried = False
        elif "_slow_path:" in ln and ln.count("ms") >= 4:  # 计时：生成/执行/收尾/总计
            nums = [int(x) for x in re.findall(r"(\d+)ms", ln)]
            if len(nums) >= 4:
                recs.append({
                    "gen": nums[0], "exec": nums[1],
                    "tail": nums[2], "total": nums[3],
                    "prompt": last_prompt, "schema": last_schema_ms,
                    "agno": last_agno_ms, "retry": last_retried,
                })
        elif "_slow_path:" in ln:  # 自校验命中 → 重试
            last_retried = True

    if not recs:
        print("未解析到计时行")
        return

    gen = [r["gen"] for r in recs]
    exe = [r["exec"] for r in recs]
    tail = [r["tail"] for r in recs]
    tot = [r["total"] for r in recs]

    print(f"样本 {len(recs)} 次提问")
    for name, xs in (("生成(LLM)", gen), ("执行(SQL)", exe), ("收尾(检索+DQ)", tail), ("总计", tot)):
        print(f"  {name:14s} 中位={median(xs):>8.0f}ms  P95={pct(xs, 0.95):>8.0f}ms  "
              f"最长={max(xs):>8.0f}ms  占总计={sum(xs) / max(1, sum(tot)) * 100:5.1f}%")

    # 分段归因：生成 计时里，schema 构建 vs agno 调用各占多少
    if schema_times or agno_times:
        print("\n分段归因（新增计时）：")
        if schema_times:
            print(f"  schema 构建(含检索) n={len(schema_times)}  中位={median(schema_times):>7.0f}ms  "
                  f"P95={pct(schema_times, 0.95):>7.0f}ms  最长={max(schema_times):>7.0f}ms")
        if agno_times:
            print(f"  agno 阶段          n={len(agno_times)}  中位={median(agno_times):>7.0f}ms  "
                  f"P95={pct(agno_times, 0.95):>7.0f}ms  最长={max(agno_times):>7.0f}ms")

    # 相关性：prompt 长度 vs 生成耗时
    xs = [r["prompt"] for r in recs]
    ys = gen
    if len(xs) > 2 and pstdev(xs) > 0 and pstdev(ys) > 0:
        mx, my = mean(xs), mean(ys)
        cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / len(xs)
        corr = cov / (pstdev(xs) * pstdev(ys))
        print(f"\n相关系数(prompt字符数 vs 生成耗时) = {corr:+.3f}"
              f"   {'← 基本无关：不是 prompt 太大导致的' if abs(corr) < 0.3 else ''}")

    # 按 prompt 分桶
    print("\n按 prompt 长度分桶（生成耗时）：")
    for lo, hi, tag in ((0, 10000, "<10K"), (10000, 14000, "10-14K"), (14000, 10**9, ">14K")):
        g = [r["gen"] for r in recs if lo <= r["prompt"] < hi]
        if g:
            print(f"  {tag:8s} n={len(g):>3}  中位={median(g):>7.0f}ms  P95={pct(g, 0.95):>7.0f}ms")

    # 重试 vs 不重试
    for flag, tag in ((True, "有自纠错重试"), (False, "无重试")):
        g = [r["gen"] for r in recs if r["retry"] == flag]
        if g:
            print(f"  {tag:10s} n={len(g):>3}  中位={median(g):>7.0f}ms  P95={pct(g, 0.95):>7.0f}ms")

    # 最慢的 8 次
    print("\n最慢 8 次：")
    for r in sorted(recs, key=lambda x: -x["gen"])[:8]:
        print(f"  生成={r['gen']:>7}ms  总计={r['total']:>7}ms  prompt={r['prompt']:>6}字符  "
              f"重试={'是' if r['retry'] else '否'}  执行={r['exec']}ms")

    # 长尾占比：>30s 的总时间占多少
    slow = [r for r in recs if r["gen"] > 30000]
    print(f"\n>30s 的 {len(slow)} 次调用，占总生成时间的 "
          f"{sum(r['gen'] for r in slow) / max(1, sum(gen)) * 100:.1f}%（{len(slow)}/{len(recs)} 次调用）")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.environ.get("TEMP", "."), "ab3.log"))
