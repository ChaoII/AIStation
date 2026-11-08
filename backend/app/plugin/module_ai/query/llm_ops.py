"""LLM 基础设施：结构化输出、IR 生成、计划、画像、运行时解析（2026-11-08 从 service.py 拆出）。

- ``_get_runtime``：把「模型 → 供应商 → env」解析成 agno 可用的 provider/model；
- ``_llm_structured``：带 schema 的结构化输出（Pydantic 校验 + 重试）；
- ``_ir_llm`` / ``_plan_llm``：对象查询 IR 与两段式计划的小模型调用；
- ``_profile_table``：给资产描述生成用的数据画像（行数/空值率/去重数）；
- ``_resolve_dialect_info``：数据源方言（决定 quote 与日期函数）。

``nl2sql_max_tokens`` / ``_ir_max_tokens`` / ``_load_ds`` 等仍归 ``service.py``，
这里用 ``_svc.`` 调用时解析。
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Any

from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.logger import log

from . import service as _svc
from .llm_schemas import PlanOut

if TYPE_CHECKING:
    from pydantic import BaseModel


class LlmOps:
    @classmethod
    async def _llm_structured(cls, prompt: str, schema: type[BaseModel], *,
                              temperature: float = 0.2, max_tokens: int = 4000,
                              runtime: dict | None = None,
                              tag: str = "aistation-suggest") -> Any:
        """结构化输出：走 agno ``output_schema``，由模型侧 JSON schema 约束结果。

        相比「提示词里要求 JSON + 事后手工解析」（旧 ``_llm_json`` 路径），
        这里把结构约束交给模型服务端，返回**已校验**的 ``schema`` 实例。

        - ``runtime`` 为空时自行 ``_get_runtime()``（调用方已有 runtime 时可传入复用）；
        - 超时只在 agno **之外**用 ``asyncio.wait_for`` 兜底（agno 的 timeout 仅单次 HTTP）；
        - 网关不回原生结构时，兼容 dict / JSON 文本两种形态兜底解析。
        """
        from agno.agent import Agent
        from agno.models.openai.like import OpenAILike

        from app.plugin.module_ai.models.service import build_headers

        if runtime is None:
            try:
                runtime = await cls._get_runtime()
            except Exception as e:  # noqa: BLE001
                raise CustomException(msg=f"未配置可用的辅助模型：{e}")
        cfg = await cls._cfg()
        model = OpenAILike(
            id=runtime["model"], base_url=runtime["base_url"],
            api_key=runtime.get("api_key") or "sk-none",
            temperature=temperature, max_tokens=max_tokens, timeout=90,
            # 辅助任务只要结果，压住思考避免长尾（与 NL2SQL 的思考控制结论一致）
            extra_body={"reasoning_effort": "low"},
            default_headers=build_headers(
                runtime["base_url"], runtime.get("extra_headers"), tag),
        )
        agent = Agent(model=model, output_schema=schema, telemetry=False, markdown=False)
        try:
            resp = await asyncio.wait_for(
                agent.arun(prompt),
                timeout=cls._cfg_int(cfg, "nl2sql_call_timeout", 90),
            )
        except asyncio.TimeoutError:
            raise CustomException(msg="大模型辅助调用超时，请稍后重试")
        except Exception as e:  # noqa: BLE001
            raise CustomException(msg=f"大模型辅助调用失败：{str(e)[:200]}")
        content = getattr(resp, "content", None)
        if isinstance(content, schema):
            return content
        if content is None or (isinstance(content, str) and not content.strip()):
            # 实测：推理型模型可能把 max_tokens 全花在思考上，最终 content 为空
            raise CustomException(msg="大模型未返回结构化结果（思考可能耗尽输出预算，请重试或减小输入规模）")
        try:
            if isinstance(content, dict):
                return schema.model_validate(content)
            return schema.model_validate(cls._parse_llm_json(str(content)))
        except Exception as e:  # noqa: BLE001
            log.warning("[query] 结构化输出解析失败：{}｜模型原文：{}",
                        str(e)[:100], str(content)[:200])
            raise CustomException(msg=f"大模型返回结构不完整：{str(e)[:100]}")

    @classmethod
    async def _ir_llm(cls, prompt: str, runtime: dict) -> str:
        """一次 LLM 调用生成对象查询 IR（复用 agno，与 NL2SQL 同源）。

        模型解析走 ``_get_runtime()``：``usage`` 精确匹配优先（query → chat → 默认），
        因此这里用的就是「模型配置」里那个默认 chat 模型（本项目为 LLM-284B-MXFP4）。
        """
        import asyncio as _asyncio

        from agno.agent import Agent
        from agno.models.openai.like import OpenAILike

        from app.plugin.module_ai.models.service import build_headers

        cfg = await cls._cfg()
        model = OpenAILike(
            id=runtime["model"], base_url=runtime["base_url"],
            api_key=runtime.get("api_key") or "sk-none",
            # ⚠️ 必须用带下限的预算：本机模型是**推理型**，thinking 计入 max_tokens，
            # 预算太小会被思考吃光 → finish_reason=length、正文为空（实测 1200 就会空）。
            # 可用 `object_query_max_tokens` 单独调大（默认沿用 NL2SQL 的预算）。
            temperature=0.0,
            max_tokens=_svc._ir_max_tokens(cfg),
            timeout=60,
            # 思考压到 low：实测**原始调用** A(enable_thinking=false)=19.0s ｜
            # B(reasoning_effort=low)=10.9s ｜ C(默认)=17.8s —— low 最快，故用 low。
            # ⚠️ 注意 agno 包装会额外耗时（裸调用 11~19s，经 Agent 后 17~32s），
            #    所以下面的 wait_for 超时必须留足余量（见 object_query_call_timeout 的说明）。
            extra_body={"reasoning_effort": "low"},
            default_headers=build_headers(
                runtime["base_url"], runtime.get("extra_headers"), "aistation-query-ir"),
        )
        agent = Agent(model=model, telemetry=False, instructions=prompt)

        async def _call() -> str:
            resp = await _asyncio.wait_for(
                agent.arun("请严格按上面的格式只输出对象查询 JSON。"),
                timeout=cls._cfg_int(cfg, "object_query_call_timeout", 20),
            )
            return (getattr(resp, "content", "") or "").strip()

        t_start = time.perf_counter()
        out = await _call()
        elapsed = time.perf_counter() - t_start
        if not out and elapsed <= 8.0:
            # 偶发空正文（推理型模型把预算用在 thinking / 网关抖动）：**只在快速空时重试**。
            # 慢空（>8s）说明模型在这条 prompt 上就是吐不出来，再等一轮只是白花 20 秒
            # （实测对象查询每题耗 30s×2，一次问数被拖到 158s）。
            log.warning("[query] IR 首次空正文（耗时 {}ms），快速重试一次", int(elapsed * 1000))
            t0 = time.perf_counter()
            try:
                out = await _call()
            except Exception as e:  # noqa: BLE001
                log.warning(f"[query] IR 重试失败 [{type(e).__name__}]: {str(e)[:100]}")
                out = ""
            log.warning("[query] IR 重试耗时={}ms", int((time.perf_counter() - t0) * 1000))
        elif not out:
            log.warning("[query] IR 慢空（{}ms），不重试，直接降级 NL2SQL", int(elapsed * 1000))
        return out

    @classmethod
    async def _plan_llm(cls, prompt: str, runtime: dict, temperature: float = 0.0) -> str:
        """计划阶段的一次 LLM 调用（只出 JSON 计划，不写 SQL）。统一走 agno。

        用 agno ``output_schema``（模型原生 JSON schema）约束计划结构，
        返回规范化后的计划 JSON 文本，交由 ``plan.parse_plan`` 解析与表名过滤。
        """
        out = await cls._llm_structured(
            prompt, PlanOut, temperature=temperature,
            max_tokens=_svc.nl2sql_max_tokens(None), runtime=runtime,
            tag="aistation-query-plan")
        return json.dumps(out.model_dump(), ensure_ascii=False)

    @classmethod
    async def _profile_table(cls, tname: str, colnames: list[str]) -> dict:
        """对表做轻量数据画像：行数 + 每列可空率/基数/低基数枚举分布。"""
        from sqlalchemy import text as _t

        profile: dict = {"table": tname, "rows": 0, "cols": {}}
        if not tname or not colnames:
            return profile
        try:
            async with async_db_session() as db:
                rc = (await db.execute(_t(f'SELECT COUNT(*) FROM "{tname}"'))).scalar() or 0
                profile["rows"] = int(rc)
                for c in colnames:
                    info: dict = {}
                    try:
                        row = (await db.execute(
                            _t(f'SELECT COUNT(*) FILTER (WHERE "{c}" IS NULL) AS nn, '
                                f'COUNT(DISTINCT "{c}") AS nd FROM "{tname}"')
                        )).fetchone()
                        nn = int(row[0] or 0)
                        nd = int(row[1] or 0)
                        info["null_pct"] = round(nn * 100.0 / rc, 1) if rc else 0
                        info["distinct"] = nd
                        if nd <= 12 and nd > 0:
                            vals = [
                                str(r[0]) for r in (await db.execute(
                                    _t(f'SELECT DISTINCT "{c}" FROM "{tname}" WHERE "{c}" IS NOT NULL LIMIT 12')
                                )).fetchall()
                            ]
                            info["values"] = vals[:12]
                    except Exception:  # noqa: BLE001
                        info = {}
                    profile["cols"][c] = info
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 画像失败 {tname}: {e}")
        return profile

    @classmethod
    async def _get_runtime(cls) -> dict:
        from app.plugin.module_ai.models.service import AiModelService

        # 顺序很关键：`get_runtime_model(usage)` 会把 **usage 为空**的模型也算命中
        # （"通用"语义，兼容旧数据），于是专门为 chat 配的本地模型根本不参与，
        # 问数被顶到那个"通用"模型上——而它可能是额度受限的外部网关，
        # 表现为模型返回一段错误文本，最后报成「仅允许 SELECT 查询」，
        # 完全看不出真实原因。所以这里要求**精确匹配用途**优先。
        first = None
        for u in ("query", "chat"):
            r = await AiModelService.get_runtime_model(u)
            first = first or r
            if r and r.get("usage") == u:
                return r
        if first:
            return first
        runtime = await AiModelService.get_runtime_model()
        if not runtime:
            raise CustomException(msg="未配置可用的 chat 模型")
        return runtime

    @classmethod
    async def _resolve_dialect_info(cls, datasource: str) -> tuple[dict, str]:
        """按数据源字符串解析方言配置。

        返回 ``(dialect配置, 数据源类型)``。``datasource`` 取值：
        - ``system`` / ``None`` → PostgreSQL；
        - ``ds:{id}`` → 读该数据源模型的 ``type``（postgres/mysql/sqlite/file/api）；
        - 其它 / 读取失败 → 回退 PostgreSQL（不报错，避免因方言问题整题失败）。

        纯逻辑解析在 ``dialect.resolve_dialect`` 里做；此处只负责「数据源字符串 →
        数据源类型」这一段，本文件已用 ``_svc._ds_cfg_from_model`` 统一暴露类型。
        """
        from .dialect import resolve_dialect

        cfg = await cls._cfg()
        if not cls._cfg_bool(cfg, "multi_dialect_enabled", True):
            # 开关关闭：回到旧的「统一 PostgreSQL 提示词」行为。
            return resolve_dialect("postgres"), "postgres"
        if not datasource or datasource == _svc.SYSTEM_DS:
            return resolve_dialect("postgres"), "postgres"
        if str(datasource).startswith("ds:"):
            try:
                _id = int(str(datasource).split(":")[-1])
                _ds = await _svc._load_ds(_id)
                _t = (_svc._ds_cfg_from_model(_ds).get("type") or "postgres")
                return resolve_dialect(_t), _t
            except Exception as e:  # noqa: BLE001
                log.warning("[query] 读取数据源方言失败，回退 PostgreSQL：[{}] {}",
                            type(e).__name__, str(e)[:80])
                return resolve_dialect("postgres"), "postgres"
        return resolve_dialect("postgres"), "postgres"
