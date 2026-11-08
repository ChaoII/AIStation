"""多轮改写：追问补全为自包含问题（2026-11-08 从 service.py 拆出）。

开关默认关：改写要多一次 LLM 调用，且历史不完整时容易把「它」补错对象。
``_query_conventions`` 给改写提示词提供方言/命名约定，``_relevant_tables`` 收敛候选表。
"""
from __future__ import annotations

from app.core.logger import log

from . import service as _svc


class RewriteOps:
    @classmethod
    async def _maybe_rewrite(cls, question: str, session_id: int | None,
                             datasource: str | None = None) -> str:
        """多轮查询重写（G7）：把「那上周呢 / 换成华东呢」补全成自包含问题。

        - 仅在 ``query_rewrite_enabled`` 且 ``needs_rewrite`` 判定为「不自包含」时，
          才发生一次 LLM 调用；否则**零额外开销**（成本纪律）。
        - 重写失败 / 结果与原文相同 / 过长 → 用原问题（**不改变原意**，宁可不用）。
        - 重写后的自包含问题会在 `ask`/`ask_stream` 里**重新走一遍路由**（可命中指标
          快路径或对象查询），不硬进 NL2SQL。
        - 越权防护：重写只改文字，对象/表白名单与权限校验仍在路由与执行层把关。
        """
        from .rewrite import (
            build_rewrite_prompt,
            finalize_rewrite,
            needs_rewrite,
            recent_history,
        )

        q = (question or "").strip()
        if not q:
            return q
        cfg = await cls._cfg()
        if not cls._cfg_bool(cfg, "query_rewrite_enabled", False):
            return q
        try:
            msgs = await cls.list_messages(session_id) if session_id else []
        except Exception as e:  # noqa: BLE001
            log.warning("[query] 读会话历史失败，跳过重写：[{}] {}", type(e).__name__, str(e)[:80])
            msgs = []
        hist = recent_history(msgs)
        if not needs_rewrite(q, hist):
            return q
        try:
            runtime = await cls._get_runtime()
        except Exception as e:  # noqa: BLE001
            log.warning("[query] 获取模型失败，跳过重写：[{}] {}", type(e).__name__, str(e)[:80])
            return q
        try:
            text = await cls._rewrite_llm(build_rewrite_prompt(q, hist), runtime)
        except Exception as e:  # noqa: BLE001
            log.warning("[query] 多轮重写调用失败，用原问题：[{}] {}",
                        type(e).__name__, str(e)[:80])
            return q
        rw = finalize_rewrite(q, text)
        if rw and rw != q:
            log.warning("[query] 多轮重写：{} → {}", q[:40], rw[:40])
            return rw
        return q

    @classmethod
    async def _rewrite_llm(cls, prompt: str, runtime: dict) -> str:
        """一次 LLM 调用把追问重写为自包含问题（G7，复用 agno）。

        与 ``_ir_llm`` 同款：``_get_runtime()`` 解析模型 → ``OpenAILike`` → ``Agent``。
        LLM 调用本身有 ``wait_for`` 兜底超时；失败由调用方 `_maybe_rewrite` 降级为
        直接用原问题。
        """
        import asyncio as _asyncio

        from agno.agent import Agent
        from agno.models.openai.like import OpenAILike

        from app.plugin.module_ai.models.service import build_headers

        cfg = await cls._cfg()
        model = OpenAILike(
            id=runtime["model"], base_url=runtime["base_url"],
            api_key=runtime.get("api_key") or "sk-none",
            temperature=0.0, max_tokens=_svc.nl2sql_max_tokens(cfg), timeout=60,
            # 重写是纯文本改写，不需要深度推理：压掉思考速度更快。
            extra_body={"reasoning_effort": "low"},
            default_headers=build_headers(
                runtime["base_url"], runtime.get("extra_headers"), "aistation-query-rewrite"),
        )
        agent = Agent(model=model, telemetry=False, instructions=prompt)
        resp = await _asyncio.wait_for(
            agent.arun("请重写上面的问题。"),
            timeout=cls._cfg_int(cfg, "query_rewrite_call_timeout", 60),
        )
        return (getattr(resp, "content", "") or "").strip()

    @staticmethod
    def _relevant_tables(question: str, schema: dict, metrics: list[dict], terms: list[dict]) -> list[str]:
        """依据问题关键词，只挑相关的表（列名/表名/中文注释命中），控制注入 token 并聚焦。

        **中文注释必须参与打分**：真实业务库的表名列名是英文缩写
        （``FUEL_CB_COALBALANCE`` / ``COALMONEY``），中文问题（"煤款金额"）
        只有靠注释才匹配得上。只认英文标识符的话，检索永远命中不了。
        """
        q = question.lower()
        scores: dict[str, float] = {}
        for t in schema:
            s = 0.0
            tname = t.lower()
            if tname in q:
                s += 6.0
            for col in schema[t]:
                parts = col.split("(", 1)
                colname = parts[0].lower()
                cmt = parts[1].rstrip(")").lower() if len(parts) > 1 else ""
                # 中文注释命中权重最高——它才是业务语义
                if len(cmt) >= 2 and cmt in q:
                    s += 5.0
                if len(colname) >= 3 and colname in q:
                    s += 3.0
                for seg in colname.split("_"):
                    if len(seg) >= 3 and seg in q:
                        s += 1.0
            if s > 0:
                scores[t] = s
        # 命中太少则回退到核心业务表 + 指标涉及的表
        if len(scores) < 3:
            core = [
                "video_alarm_records", "video_cameras", "video_camera_groups",
                "train_tasks", "ai_call_logs", "sys_user", "video_edge_events",
            ]
            for c in core:
                if c in schema:
                    scores[c] = scores.get(c, 0.0) + 1.0
        if not scores:
            return []
        return sorted(scores, key=lambda t: -scores[t])[:12]

    @classmethod
    def _query_conventions(cls) -> str:
        """查询口径规范：统一业务口径，减少 LLM 生成 SQL 时的歧义（时间/用户/联表/占比）。

        ⚠️ 2026-11 试过在这里加"软删除默认排除"和"排序/取单个"两条，配对 A/B 结果：
        软删除版两轮自翻 5 题（baseline 0 题）、收益 1~2 题；排序版两轮零变化。
        两条都已移除 —— **口径这类确定规则交给代码（softdelete 模块）比交给模型稳**。
        别再往这里加"模型应该记得住的规则"，除非 A/B 证明它稳定。
        """
        return (
            "【查询口径规范】\n"
            "1. 时间口径：\n"
            "   - '最近N天/近N天' → WHERE 时间列 >= CURRENT_DATE - N\n"
            "   - '过去N月/近N月' → WHERE 时间列 >= CURRENT_DATE - INTERVAL 'N month'\n"
            "   - '某月a日到b日' → WHERE 时间列 >= 'YYYY-MM-a' AND 时间列 < 'YYYY-MM-(b+1)'（含开头不含结尾）\n"
            "   - '某日当天' → WHERE 时间列 >= '当日' AND 时间列 < '次日'\n"
            "   - '按天/每日/每天' → GROUP BY TO_CHAR(时间列,'YYYY-MM-DD') 或 date(时间列)\n"
            "   - '各小时/按小时' → SELECT EXTRACT(HOUR FROM 时间列)::int AS 小时 ... GROUP BY 小时\n"
            "   - 'YYYY年M月' → WHERE 时间列 >= 'YYYY-MM-01' AND 时间列 < 'YYYY-(M+1)-01'\n"
            "2. 用户/账号统计：一律排除已删除 → WHERE is_deleted=false；超级管理员 = is_superuser=true。\n"
            "3. 联表口径：\n"
            "   - '每个/各主实体...' → 主实体 LEFT JOIN 明细表，用 COALESCE(主实体.name,'未分组/未知') 聚合空维度；"
            "计数用 COUNT(明细表.id)（LEFT JOIN 下 NULL 不计入）。\n"
            "   - 仅'发生过/有关系的' → 用 INNER JOIN。\n"
            "   - video_alarm_records 等表无 is_deleted 字段，统计告警不要加 is_deleted 条件。\n"
            "4. 占比/平均：用 ROUND(分子*100.0/分母,2) 或 ROUND(AVG(x)::numeric,2) 保证精度。"
        )
