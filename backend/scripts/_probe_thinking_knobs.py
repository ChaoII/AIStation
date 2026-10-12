"""探针（仅诊断，不进生产路径）：网关/模型是否支持**限制思考长度**的参数。

背景：`max_tokens=8000` 被当成"思考预算"用掉了 —— 推理型模型的 thinking 计入 max_tokens，
所以难题会一直想到 8000 token（实测最长 467 秒）。若能单独限制 thinking，就能既保 SQL 输出空间
又砍掉长尾。

用法：python scripts/_probe_thinking_knobs.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", os.environ.get("ENVIRONMENT", "dev"))
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

Q = "列出每个设施下创建时间最新的测点，并按创建时间倒序排列"
CASES = [
    ("基线（max_tokens=8000）", {}, {}),
    ("reasoning_effort=low", {"reasoning_effort": "low"}, {}),
    ("enable_thinking=false", {}, {"enable_thinking": False}),
    ("chat_template.enable_thinking=false", {},
     {"chat_template_kwargs": {"enable_thinking": False}}),
]


async def main() -> None:
    from main import create_app

    create_app()  # ⚠️ 必须先初始化：否则 models 模块的 mapper 注册会失败
    from agno.agent import Agent
    from agno.models.openai.like import OpenAILike

    from app.plugin.module_ai.models.service import build_headers
    from app.plugin.module_ai.query.service import AiQueryService

    rt = await AiQueryService._get_runtime()
    print(f"模型={rt.get('model')}\n", flush=True)

    for label, model_kw, extra in CASES:
        model = OpenAILike(
            id=rt["model"], base_url=rt["base_url"], api_key=rt.get("api_key") or "sk-none",
            temperature=0.0, max_tokens=8000, timeout=120,
            default_headers=build_headers(rt["base_url"], rt.get("extra_headers"), "probe-thinking"),
            **model_kw, **({"extra_body": extra} if extra else {}),
        )
        t0 = time.perf_counter()
        try:
            from agno.agent import Agent

            a = Agent(model=model, telemetry=False, instructions="只返回 SQL，不要解释。")
            r = await a.arun(Q)
            dt = time.perf_counter() - t0
            txt = (r.content or "")
            print(f"  {label:38s} {dt:7.2f}s  输出={len(txt):>5}字符  "
                  f"{txt[:46]!r}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  {label:38s} {time.perf_counter() - t0:7.2f}s  失败={type(e).__name__}: "
                  f"{str(e)[:60]}", flush=True)


asyncio.run(main())
