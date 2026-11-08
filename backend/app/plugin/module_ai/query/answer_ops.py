"""答案与 SQL 文本处理（2026-11-08 从 service.py 拆出）。

- ``_finish_sql_stream``：流式拿到 SQL 后的收尾（校验 → 执行 → 事件序列）；
- SQL 文本：``_extract_sql`` / ``fix_sql_literals`` / ``_prune_columns`` / ``_sql_dialect``；
- JSON 容错：``_extract_json`` / ``_parse_llm_json`` / ``_first_balanced_brace``（模型输出常带解说词）；
- 呈现：``_answer`` / ``_summarize`` / ``_summarize_rows`` / ``_cn_columns``。
"""
from __future__ import annotations

import json
import re
import time

from app.core.exceptions import CustomException

from . import service as _svc
from .model import AiQueryMessageModel


class AnswerOps:
    @classmethod
    async def _finish_sql_stream(cls, question: str, session_id: int, sql: str,
                                 datasource: str, auth) -> list[dict]:
        """流式问数的**唯一出口**：执行 → 落库 → 组装事件。

        抽出来是为了让「缓存命中的 SQL」和「刚生成的 SQL」走**同一段**执行逻辑
        （旧实现只有生成路径，缓存/代价护栏/空结果提示都只存在于非流式分支）。
        """
        try:
            # 代价护栏（对齐非流式 `_slow_path`）：系统库先 EXPLAIN 估行数，超上限直接拒绝
            if datasource in (_svc.SYSTEM_DS, None):
                try:
                    er = await cls._explain_rows(sql)
                    max_rows = cls._cfg_int(await cls._cfg(), "query_cost_max_rows", 50000)
                    if er > max_rows:
                        msg = (f"查询代价过高(预计{er}行>上限{max_rows})，"
                               "请改为聚合/加条件/限制范围")
                        await cls._save_message(session_id, question, path="slow",
                                                datasource=datasource, sql=sql, rows=[],
                                                is_error=True, summary=msg)
                        return [{"type": "error", "message": msg}]
                except CustomException as e:  # noqa: BLE001
                    msg = f"SQL 校验失败：{e.msg}"
                    await cls._save_message(session_id, question, path="slow",
                                            datasource=datasource, sql=sql, rows=[],
                                            is_error=True, summary=msg)
                    return [{"type": "error", "message": msg}]
                except Exception:  # noqa: BLE001
                    pass  # EXPLAIN 本身失败不阻断执行（非 PG / 特殊 SQL）
            res = await cls._execute_one(sql, datasource, auth, question)
            cols = res.get("columns") or []
            rows = res.get("rows") or []
            # Grounding **必须落库**（刷新/重开会话后「召回的表 / 本体对象」标签要能复原）
            retrieved = await cls._recall_grounding(question, datasource)
            ont_used = _svc._scan_ont_tables(sql)
            msg = await cls._save_message(
                session_id, question, path="slow", datasource=datasource,
                sql=sql, columns=cols, rows=rows,
                result_rows=len(rows), took_ms=res.get("took_ms", 0), cached=False,
                summary="以下是根据你的问题生成的结果：",
                grounding={"retrieved": retrieved, "ontology_used": ont_used},
            )
            # 只在**真有数据**时写 SQL 缓存（全 NULL 结果会把空表 SQL 缓存住，越查越空）
            flat = [v for r in rows for v in (r if isinstance(r, (list, tuple)) else [r])]
            if flat and any(v is not None for v in flat):
                _svc._sql_cache_set(question, datasource, sql, _svc._auth_scope(auth))
            return [
                {"type": "result", "columns": cols, "rows": rows, "result_rows": len(rows),
                 "sql": sql, "took_ms": res.get("took_ms", 0),
                 "applied": res.get("applied") or [], "policy_ids": res.get("policy_ids") or [],
                 "retrieved": retrieved, "ontology_used": ont_used, "message_id": msg.id,
                 "dq_warning": await cls._dq_warning_for_sql(sql)},
                {"type": "answer", "summary": "以下是根据你的问题生成的结果："},
                {"type": "done", "message_id": msg.id},
            ]
        except Exception as e:  # noqa: BLE001
            await cls._save_message(session_id, question, path="slow", datasource=datasource,
                                    sql=sql, rows=[], is_error=True, summary=f"查询失败：{e}")
            return [{"type": "error", "message": f"查询失败：{e}"}]

    @classmethod
    def _extract_sql(cls, s: str) -> str:
        """从模型输出里抠出 SQL。

        工具化 Agent 按指令要求输出 JSON（``{"sql": "<SELECT ...>"}``），
        而旧实现只做「去围栏 + 取第一个 select + 截到分号」——
        JSON 的**尾部 `"}` 会被留下**，SQL 因此解析不出 Select 节点，
        整条问数报「仅允许 SELECT 查询」而失败（既有缺陷，已用 git stash 复现确认）。
        """
        s = (s or "").strip()
        # 1) JSON 解包（工具化 Agent 的正常输出形态）
        if s.startswith("{"):
            try:
                import json as _json

                obj = _json.loads(s)
                if isinstance(obj, dict) and obj.get("sql"):
                    s = str(obj["sql"])
            except Exception:  # noqa: BLE001
                # JSON 被截断时的兜底：正则捞出 "sql": "..." 的内容
                m = re.search(r'"sql"\s*:\s*"(.*?)"\s*\}?\s*$', s, re.S)
                if m:
                    s = m.group(1).replace('\\"', '"').replace("\\n", "\n")
        # 2) 去 markdown 代码块围栏
        s = re.sub(r"```[a-zA-Z]*", "", s).strip()
        # 3) 取第一个 SELECT 开始
        idx = s.lower().find("select")
        if idx >= 0:
            s = s[idx:]
        # 4) 截到第一个分号，保留多行 SQL（JOIN/GROUP BY/窗口函数通常跨行）
        s = re.split(r";", s, maxsplit=1)[0].strip()
        # 5) 去掉 JSON 残留的尾巴（只去 } ] 与空白，**不动引号**，
        #    否则会把 `... = 'ONLINE'` 的收尾引号一起吃掉
        s = re.sub(r"[}\]]+\s*$", "", s).strip()
        return s

    @classmethod
    async def _sql_dialect(cls, datasource: str) -> str:
        """数据源 → **sqlglot 读方言**名（编译器/解析器共用，未知回退 postgres）。

        外部库可能是 MySQL/SQLite：把 PG 语法套过去会直接产生非法 SQL（反引号、
        标识符大小写、函数名）。``api`` / ``file`` 这类没有 SQL 方言的源按 PG 处理
        （它们本来也不走 SQL 执行链路）。
        """
        if not datasource or datasource == _svc.SYSTEM_DS:
            return "postgres"
        key = str(datasource)
        hit = _svc._SQL_DIALECT_CACHE.get(key)
        if hit and time.time() - hit[0] <= _svc._SQL_DIALECT_TTL:
            return hit[1]
        ds_type = ""
        try:
            _dialect, ds_type = await cls._resolve_dialect_info(datasource)
        except Exception:  # noqa: BLE001 - 方言解析失败按 PG 兜底（不阻断判定）
            return "postgres"
        value = {"mysql": "mysql", "sqlite": "sqlite"}.get(
            str(ds_type or "").lower(), "postgres")
        if len(_svc._SQL_DIALECT_CACHE) >= 20:
            _svc._SQL_DIALECT_CACHE.clear()
        _svc._SQL_DIALECT_CACHE[key] = (time.time(), value)
        return value

    @classmethod
    def fix_sql_literals(cls, sql: str, value_map: dict[tuple[str, str], list[str]]) -> tuple[str, list[str]]:
        """把 SQL 里**归一后相等**的字面量换成库里的原始写法（值匹配纠错）。

        为什么：用户/模型常写成 ``'烟煤 '``（尾随空格）、``'FL'`` vs ``'fl'``、
        全角 ``'ＡＢ'``，而库里存的是 ``'烟煤'``。语义完全相同，但等值比较查不到行 ——
        这正是 Genie 的 entity matching 想解决的问题。

        **只做"归一后相等"的替换**（strip / 全角→半角 / ASCII 大小写），
        不做模糊匹配（编辑距离），避免把语义改掉。
        """
        if not sql or not value_map:
            return sql, []
        by_norm: dict[str, str] = {}
        for vals in value_map.values():
            for v in vals:
                if isinstance(v, str) and v:
                    by_norm.setdefault(cls._norm_value(v), v)
        if not by_norm:
            return sql, []
        fixes: list[str] = []

        def _sub(m: re.Match) -> str:
            raw = m.group(1)
            canon = by_norm.get(cls._norm_value(raw))
            if canon and canon != raw:
                fixes.append(f"{raw!r} → {canon!r}")
                return "'" + canon.replace("'", "''") + "'"
            return m.group(0)

        return cls._SQL_LITERAL_RE.sub(_sub, sql), fixes

    @staticmethod
    def _norm_value(v: str) -> str:
        """值归一：去首尾空白 + 全角转半角 + 大小写。用于判断"是不是同一个值"。"""
        import unicodedata

        return unicodedata.normalize("NFKC", str(v or "")).strip().lower()

    @classmethod
    async def _cn_columns(cls, columns: list, sql: str) -> list:
        """把结果列名里的**英文属性名换成中文名**（本体是唯一来源）。

        模型经常写 `SELECT COUNT(*) AS c` 或直接 `SELECT status`，
        表格里就出现 `c` / `status` 这种看不懂的列头。
        """
        cols = list(columns or [])
        if not cols or not sql:
            return cols
        tables = _svc._scan_ont_tables(sql)
        if not tables:
            return cols
        mapping: dict[str, str] = {}
        try:
            from app.plugin.module_ai.ontology import semantic as _sem

            ctx = await _sem.semantic_context()
            code_of = await _sem.object_table_map()
            want_codes = {code_of.get(t) for t in tables} - {None}
            for code in want_codes:
                for p in ctx["properties"].get(code, []):
                    if p["name"] and p["name"] != p["code"]:
                        mapping.setdefault(p["code"], p["name"])
        except Exception:  # noqa: BLE001
            return cols
        if not mapping:
            return cols
        return [mapping.get(str(c).strip().strip('"'), c) for c in cols]

    @classmethod
    def _extract_json(cls, s: str) -> str:
        """从模型输出中提取 JSON 文本。

        1. 先剥离 ```json ... ``` 代码块围栏；
        2. 剥离后若已是合法 JSON，直接返回；
        3. 若模型在 JSON 前后附带了自然语言解释（无围栏/无换行），
           扫描文本找第一个**平衡**的 ``{ ... }`` 并截取该子串返回；
        4. 均失败则原样返回，交由 ``json.loads`` 报错兜底。
        """
        t = (s or "").strip()
        if t.startswith("```"):
            t = t.split("\n", 1)[-1] if "\n" in t else t
            t = t.rsplit("```", 1)[0].strip()
        # 已是合法 JSON：直接返回，避免误截取解释里的花括号
        try:
            json.loads(t)
            return t
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        obj = cls._first_balanced_brace(t)
        return obj if obj is not None else t

    @classmethod
    def _parse_llm_json(cls, raw: str) -> dict:
        """解析模型返回的 JSON 文本：``_extract_json`` + ``json.loads``。

        仅作为 ``_llm_structured`` 的兜底（网关未回原生结构化输出时用），
        非法 JSON 或非对象 → 抛可读 ``CustomException``。
        """
        try:
            parsed = json.loads(cls._extract_json(raw))
        except (json.JSONDecodeError, TypeError, ValueError):
            raise CustomException(msg="大模型返回不是有效 JSON")
        if not isinstance(parsed, dict):
            raise CustomException(msg="大模型返回不是有效 JSON")
        return parsed

    @staticmethod
    def _first_balanced_brace(t: str) -> str | None:
        """取文本中第一个**平衡**的 ``{ ... }`` 子串（跳过字符串内花括号与转义）。

        用于模型在 JSON 前后附带自然语言解释（无围栏、无换行）时，
        精确截取 JSON 对象本身。找不到平衡对象返回 ``None``。
        """
        start = t.find("{")
        if start < 0:
            return None
        depth = 0
        in_str = False
        escape = False
        for i in range(start, len(t)):
            c = t[i]
            if in_str:
                if escape:
                    escape = False
                elif c == "\\":
                    escape = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return t[start:i + 1]
        return None

    @classmethod
    def _prune_columns(cls, question: str, labels: list[str]) -> tuple[list[str], int]:
        """按问题裁剪列清单：**保留问句提到的列 + 结构性列**，其余折叠。

        依据：实测 12 张表 × 约 40 列 ≈ 480 个列名，而生成的 SQL 中位数只用
        1 张表、2 个标识符 —— 99% 的 schema 是噪声（prompt 里 84% 的字数来自这里）。

        ⚠️ 本方法曾被一次"整段替换"误删（编译不报错、运行时 AttributeError），
        删掉的后果是所有慢路径问题全挂 —— 改动这段区域时务必跑一次真实提问验证。
        """
        q_grams = _svc._bigrams(question)
        q_low = (question or "").lower()
        kept: list[str] = []
        for lab in labels:
            code = lab.split("(", 1)[0]
            cn = lab[len(code):].strip("() ")
            hit = cls._STRUCT_COL_RE.search(code) is not None
            if not hit and code.lower() in q_low:
                hit = True
            if not hit and _svc._bigrams(cn) & q_grams:
                hit = True
            if hit:
                kept.append(lab)
        return kept, len(labels)

    @classmethod
    def _summarize_rows(cls, columns: list, rows: list) -> str:
        """把结果说成**一句人话**。

        原先慢路径的摘要是硬编码的「以下是根据你的问题生成的结果：」——
        等于没回答。用户问"一共有多少条告警记录"，看到的却是这句话。
        """
        cols = list(columns or [])
        rows = list(rows or [])
        if not rows:
            return "没有查到符合条件的数据"
        if not cols:
            return f"共 {len(rows)} 行结果"
        if len(rows) == 1 and len(cols) == 1:
            v = rows[0][0]
            name = str(cols[0]).strip()
            if name.lower() in cls._LAZY_COLS:
                return f"结果是 {v}"
            return f"{name}：{v}"
        if len(rows) == 1:
            parts = [f"{c} {v}" for c, v in zip(cols, rows[0], strict=False)]
            return "；".join(parts[:5])
        # 多行：说清规模 + 给个头一条，让用户知道看到了什么
        head = "；".join(f"{c} {v}" for c, v in zip(cols, rows[0], strict=False) if
                         str(c).lower() not in cls._LAZY_COLS) or \
               "；".join(f"{c} {v}" for c, v in zip(cols, rows[0], strict=False))
        return f"共 {len(rows)} 行；第一行：{head}"

    @classmethod
    def _summarize(cls, metric: dict, res: dict) -> str:
        if not res["rows"]:
            return "暂无数据"
        if len(res["rows"]) == 1 and len(res["columns"]) == 1:
            v = res["rows"][0][0]
            return f"{metric.get('name', '')}为 {v} {metric.get('unit', '')}".strip()
        return f"共 {len(res['rows'])} 行结果"

    @classmethod
    def _answer(cls, msg: AiQueryMessageModel, metric: dict | None = None, sql: str | None = None,
                retrieved: dict | None = None) -> dict:
        # 置信度：快路径(指标确定性)=1.0；慢路径(LLM生成)=0.85；错误=0
        confidence = 0.0
        evidence = None
        if not msg.is_error:
            if msg.path == "fast":
                confidence = 1.0
                src = "本体指标"
            elif msg.path == "object":
                # 对象查询：语义由本体定义、执行由实例层确定性完成，正确性高于 LLM 直写 SQL
                confidence = 0.95
                src = "本体对象查询"
            else:
                confidence = 0.85
                src = "LLM 生成"
            evidence = {
                "source": src,
                "ontology_used": _svc._scan_ont_tables(msg.sql or sql or ""),
                "retrieved_tables": (retrieved or {}).get("tables") or [],
            }
        return {
            "id": msg.id, "session_id": msg.session_id, "path": msg.path,
            "datasource": msg.datasource, "sql": msg.sql or sql or "",
            "columns": msg.columns or [], "rows": msg.rows or [],
            "summary": msg.summary or "", "result_rows": msg.result_rows or 0,
            "took_ms": msg.took_ms or 0, "cached": msg.cached, "is_error": msg.is_error,
            "metric": metric,
            "ontology_used": _svc._scan_ont_tables(msg.sql or sql or ""),
            "retrieved": retrieved,
            "confidence": confidence, "evidence": evidence,
        }
