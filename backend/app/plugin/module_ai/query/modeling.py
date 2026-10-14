"""大模型自动建模：LLM 调用（agno）+ 容错解析 + 口径验证 + 幂等落库。

设计依据：`docs/superpowers/specs/2026-10-14-semantic-layer-fusion-design.md` §3。

要点：
1. **LLM 一律走 agno**（复用 `AiQueryService._ir_runtime` 的模型解析），不新增直连。
2. 解析必须**容错**（围栏/噪声/截断）——模型的 JSON 输出从不保证干净。
3. 生成的一切都**幂等**落库、可反复跑。
"""
from __future__ import annotations

import json
import re

from app.core.logger import log

_JSON_FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


def _salvage_objects(raw: str) -> list[dict]:
    """从**被截断**的 JSON 里救回完整对象（花括号配平扫描，跳过字符串内的括号）。"""
    out: list[dict] = []
    stack: list[int] = []
    in_str = False
    esc = False
    for i, ch in enumerate(raw):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            stack.append(i)
        elif ch == "}" and stack:
            start = stack.pop()
            try:
                obj = json.loads(raw[start : i + 1])
            except Exception:  # noqa: BLE001
                obj = None
            if isinstance(obj, dict):
                out.append(obj)
    return out


def parse_json_objects(text: str) -> list[dict]:
    """容错解析 LLM 输出里的**对象列表**（围栏/噪声/包裹/截断都兜住）。

    返回 `list[dict]`；解析不出返回 `[]`（**不抛异常**）。
    """
    raw = _JSON_FENCE_RE.sub("", (text or "").strip()).strip()
    if not raw:
        return []

    # 1) 先试数组（若先抽 {...} 只会拿到第一条）
    s, e = raw.find("["), raw.rfind("]")
    if 0 <= s < e:
        try:
            arr = json.loads(raw[s : e + 1])
            if isinstance(arr, list):
                return [x for x in arr if isinstance(x, dict)]
        except Exception:  # noqa: BLE001
            pass

    # 2) 再试对象：取任一列表值（metrics/objects/annotations/cases/items），或裸对象
    s2, e2 = raw.find("{"), raw.rfind("}")
    if 0 <= s2 < e2:
        try:
            data = json.loads(raw[s2 : e2 + 1])
        except Exception:  # noqa: BLE001
            data = None
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                    return v
            return [data]
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]

    # 3) 兜底：输出被截断 → 花括号配平救回完整对象
    return [x for x in _salvage_objects(raw) if isinstance(x, dict)]


async def model_llm(prompt: str, *, max_tokens: int = 4000, timeout: int = 120) -> str:
    """一次建模 LLM 调用（**走 agno**，与问数同源模型）。

    失败一律 `log.warning` + 返回 `""`（不抛）——调用方按"无产出"处理。
    """
    try:
        from agno.agent import Agent
        from agno.models.openai.like import OpenAILike

        from app.plugin.module_ai.models.service import build_headers

        from .service import AiQueryService

        runtime = await AiQueryService._ir_runtime()
        model = OpenAILike(
            id=runtime["model"], base_url=runtime["base_url"],
            api_key=runtime.get("api_key") or "sk-none",
            temperature=0.0, max_tokens=max_tokens, timeout=timeout,
            default_headers=build_headers(
                runtime["base_url"], runtime.get("extra_headers"), "aistation-modeling"),
        )
        agent = Agent(model=model, telemetry=False)
        resp = await agent.arun(prompt)
        content = getattr(resp, "content", "") or ""
        if not content.strip():
            log.warning("[modeling] LLM 返回空正文")
        return content
    except Exception as e:  # noqa: BLE001
        log.warning(f"[modeling] LLM 调用失败 [{type(e).__name__}]: {str(e)[:120]}")
        return ""
