"""提示词上下文：``_build_schema_context``（2026-11-08 从 service.py 拆出）。

把「按主体裁剪后的表/列 + 指标 + 术语 + 本体」拼成 LLM 提示词里的 schema 段。
短时缓存 key 里带**配置签名 + 主体签名**：不同用户不能复用同一份「有权 schema」，
否则等于绕过了权限裁剪（这是权限闭环的一部分，不是性能优化）。

进程级状态（``_OBJECT_CTX`` / ``_BYPASS_CACHE`` / ``_SCHEMA_CTX_CACHE`` 等）仍归
``service.py``，这里通过 ``_svc.`` 在调用时读取：既能读到最新值，也让测试对
``service._BYPASS_CACHE`` 之类的 patch 继续生效。
"""
from __future__ import annotations

import time

from app.core.logger import log

from . import service as _svc


class ContextOps:
    @classmethod
    async def _build_schema_context(cls, question: str, datasource: str, metrics: list[dict], terms: list[dict],
                                    principal=None) -> str:
        cfg = await cls._cfg()
        # 主体指纹进缓存 key：不同用户不能复用同一份「有权 schema」提示词（否则等于绕过裁剪）
        from app.plugin.module_ai.query.policy.context import (
            build_context_scope as _build_scope,
        )
        from app.plugin.module_ai.query.policy.context import (
            scope_signature as _scope_sig,
        )
        _sig = _scope_sig(principal)
        # 命中短时缓存直接返回（见函数尾部写入处）。key 与写入处必须完全一致
        # （含配置签名）—— 两处拼法不一致 = 缓存永不命中，白算一遍。
        if not _svc._OBJECT_CTX.get() and not _svc._BYPASS_CACHE.get():
            _hit = _svc._SCHEMA_CTX_CACHE.get(f"{datasource or ''}|{question}|{_svc._cfg_sig(cfg)}|{_sig}")
            if _hit and time.time() - _hit[0] <= _svc._SCHEMA_CTX_TTL:
                return _hit[1]
        lines = []
        # 当前对象上下文：**确定性注入**（对齐 Palantir Retrieval Context），放在最前面。
        octx = _svc._OBJECT_CTX.get()
        if octx:
            lines.append(octx)
        lines.append("【可用指标】")
        for m in metrics:
            if m["enabled"]:
                lines.append(f"- {m['key']}: {m['name']} ({m['description']})")
        lines.append("【术语】")
        for t in terms:
            lines.append(f"- {t['term']} -> {t['metric_key'] or t['field_path']}")
        t_c0 = time.perf_counter()
        conc = await cls._concept_context()
        t_c1 = time.perf_counter()
        if conc:
            lines.append(conc)
        lines.append("【可查询表及字段】")
        if datasource in (_svc.SYSTEM_DS, None):
            schema = await cls._system_schema()
            tmeta = await cls._asset_tmeta()
            # **先检索、再拼 prompt**：`_semantic_tables` 是本地检索（关键词+语义加权，
            # top_k=16）。旧实现先把**全部 85 个对象、1500+ 属性**塞进本体块
            # （实测 37517 字符），再把检索结果拼在后面——LLM 的前缀计算大半花在
            # 与问题无关的对象上，又慢又干扰判断。现在只带检索命中的表。
            t_r0 = time.perf_counter()
            rel = await cls._semantic_tables(question, schema, metrics, terms, datasource)
            # 生成前裁剪：无权表/列不进入提示词（执行期 guard 仍会兜底，这里是体验与防泄露）
            from app.plugin.module_ai.query.policy.context import (
                build_context_scope as _build_scope,
            )
            _scope = await _build_scope(principal, list(rel), {t: list(schema.get(t) or []) for t in rel}) if principal else None
            if _scope is not None:
                rel = [t for t in rel if t in _scope.columns]
            t_r1 = time.perf_counter()
            ont = await cls._ont_ctx_block(only_tables=set(rel))
            t_r2 = time.perf_counter()
            log.warning("[schema] 分段：概念={}ms 召回={}ms 本体块={}ms",
                        int((t_c1 - t_c0) * 1000), int((t_r1 - t_r0) * 1000),
                        int((t_r2 - t_r1) * 1000))
            if ont:
                lines.append(ont)
            for t in rel:
                cols = list(schema.get(t, []))
                if _scope is not None:
                    cols = list(_scope.columns.get(t, ()))
                    _masked = set(_scope.masked.get(t, ()))
                    cols = [f"{c}(脱敏)" if c in _masked else c for c in cols]
                meta = tmeta.get(t) or {}
                desc = meta.get("description") or ""
                scen = meta.get("business_scenarios") or ""
                nm = meta.get("alias") or ""
                dom = meta.get("domain") or ""
                head = t
                extras = []
                if nm:
                    extras.append(f"中文名:{nm}")
                if dom:
                    extras.append(f"业务域:{dom}")
                if desc:
                    extras.append(f"描述:{desc}")
                if scen:
                    extras.append(f"业务场景:{scen}")
                if extras:
                    head = f"{t}【" + "；".join(extras) + "】"
                lines.append(f"- {head}: {', '.join(cols) if cols else ''}")
            if _scope is not None and _scope.restricted:
                lines.append("注意：你只能查询上面列出的表与字段；涉及行级限制的表，"
                             "系统会自动追加过滤条件，不要尝试绕过。")
            lines.append(cls._query_conventions())
        else:
            # **自定义数据源**：原先这里**什么都不加** —— 模型对 ds:{id} 一张表、
            # 一个字段都不知道，只能瞎猜，问数必然答不对。
            # 这里把该数据源**已同步的表结构**按问题检索后注入。
            # 331 张表不能全塞，所以复用同一套关键词打分只取 top_k。
            ds_schema = await cls._ds_schema_map(datasource)
            if ds_schema:
                # 复用**统一的召回服务**（并行四路 + RRF + 阈值），
                # 而不是旧的单路关键词 —— 否则新召回只对 system 数据源生效。
                # ⚠️ 必须走带缓存的 `_semantic_tables`：`_recall_grounding` 会再查一次，
                #    用 uncached 就等于同一题做两遍向量检索（实测每次白花 1.2~1.8 秒）。
                rel = await cls._semantic_tables(question, ds_schema, metrics, terms, datasource)
                _scope = await _build_scope(principal, list(rel), {t: list(ds_schema.get(t) or []) for t in rel}) if principal else None
                if _scope is not None:
                    rel = [t for t in rel if t in _scope.columns]
                lines.append(
                    f"（数据源 {datasource}，共 {len(ds_schema)} 张表，"
                    f"下面是与问题最相关的 {len(rel)} 张）")
                # **资产目录的中文名/业务域/描述/业务场景要进 prompt**。
                # 系统数据源分支一直有这段，自定义数据源漏了 —— 实测这些文字
                # 只进了向量召回、没进模型上下文（in_prompt=False），等于白填。
                # 默认**关**：配对方差实测「开 vs 关」无差异（0.9316 vs 0.9487，
                # 差 1 道题，而同配置重跑本身就会翻 2~4 题）。且资产里 757 条有 567 条
                # 中文名 == 表名（过滤后基本加不进东西），剩下的多是"供应商管理"这类
                # 泛化说法，对选表是干扰。留开关，等资产描述质量真的提高再开。
                tmeta = (await cls._asset_tmeta()) if cls._cfg_bool(
                    cfg, "schema_asset_meta_enabled", False) else {}
                for t in rel:
                    cols = list(ds_schema.get(t, []))
                    if _scope is not None:
                        cols = list(_scope.columns.get(t, ()))
                        _masked = set(_scope.masked.get(t, ()))
                        cols = [f"{c}(脱敏)" if c in _masked else c for c in cols]
                    tmap = (_svc._DS_TYPE_CACHE.get(datasource, (0, {}))[1].get(t) or {})
                    # 列标签后面补上**数据库类型**：模型据此决定是否需要 CAST
                    # （实测 LF/RZ 是 varchar，模型写成 AVG("LF") → 函数不存在直接失败）
                    shown, total_n = cols, len(cols)
                    # 默认**开**（2026-11 配对实验）：prompt 20,991 → 10,077 字符（-52%），
                    # 单轮耗时 475/382s → 361/345s（-20%），准确率持平略升
                    # （0.9359 vs 0.9551，差异在噪声内），且内部翻转从 4 题降到 1~3 题。
                    # 依据：生成的 SQL 中位数只用 1 张表、2 个标识符，480 个列名里 99% 是噪声。
                    if cls._cfg_bool(cfg, "schema_column_prune_enabled", True):
                        shown, total_n = cls._prune_columns(question, cols)
                    rendered = [
                        f"{c}[{tmap[c.split('(', 1)[0]]}]" if c.split("(", 1)[0] in tmap else c
                        for c in shown
                    ]
                    if total_n > len(shown):
                        rendered.append(f"…（另有 {total_n - len(shown)} 列未列出，需要时按列名补充）")
                    meta = tmeta.get(t) or {}
                    extras = []
                    alias = str(meta.get("alias") or "").strip()
                    if alias and alias.lower() != str(t).lower():
                        extras.append(f"中文名:{alias}")
                    if meta.get("domain"):
                        extras.append(f"业务域:{meta['domain']}")
                    if meta.get("description") and meta["description"] != meta.get("alias"):
                        extras.append(f"描述:{meta['description']}")
                    if meta.get("business_scenarios"):
                        extras.append(f"业务场景:{meta['business_scenarios']}")
                    head = f"{t}【" + "；".join(extras) + "】" if extras else t
                    lines.append(f"- {head}: {', '.join(rendered) if rendered else ''}")
                # **本体属性的"差分"**：只注入数据源注释里没有的业务描述/枚举。
                # 实测燃料域 4985 个属性里 80/86 与列注释逐字相同、描述 0 条、枚举 0 条，
                # 全量注入只是把同一句话写两遍（和资产描述注入同一个坑）。
                # **枚举取值（从数据里取）**：口径规范里早就要求"用【取值】里的原始值"，
                # 但此前没有任何代码产出这个块。见 `_ds_enum_hints`。
                # 默认**关**：配对实测关掉更好（0.9231 → 0.9487，2 题，仍在噪声内）。
                # 口径规范里那条「用【取值】里的原始值」在关闭时不会命中歧义，
                # 因为规则本身只在 enum_hint_enabled 打开时才加。
                if cls._cfg_bool(cfg, "enum_hint_enabled", False):
                    try:
                        _vals = await cls._ds_enum_hints(datasource, rel, ds_schema)
                        if _vals:
                            lines.append("【字段取值】（低基数列的真实取值，写条件时直接用这些）")
                            lines.extend(_vals)
                    except Exception as e:  # noqa: BLE001
                        log.warning(f"[query] 枚举取值注入失败（忽略）: {str(e)[:80]}")
                lines.append(cls._query_conventions())
                # 该库表名/字段名为英文大写且大小写敏感：不加双引号会被 PG 小写化 → 找不到表。
                lines.append(
                    "【标识符大小写】本数据源的表名/字段名为**英文大写且大小写敏感**，"
                    'SQL 中必须用双引号引用：如 FROM "FUEL_CB_COALBALANCE"、SUM("COALMONEY")。'
                )
                lines.append(
                    "【数值列类型】若某列标注为 character varying/text 但语义是数值（如 RZ、LF、"
                    'BALANCEQTY），聚合前必须先转换：AVG(CAST("LF" AS numeric))，'
                    "不要把 CAST 放在聚合外面（CAST(AVG(...)) 会因 avg(varchar) 不存在而失败）。"
                )
        lines.append("【示例问题→SQL】")
        for eg in await cls._dynamic_fewshots(question, datasource):
            lines.append(f"问：{eg['q']}")
            lines.append(f"SQL：{eg['sql']}")
        ctx = "\n".join(lines)
        # 同一问题的 prompt 上下文短时缓存：自纠错重试、流式与非流式、以及「同一题再问一次」
        # 都会重复构建（首题实测 4~12 秒，主要花在向量召回），缓存后重试只剩几十毫秒。
        # 有对象上下文（每次请求不同）时不缓存，避免串题。
        # ⚠️ key 必须带**配置签名**：prompt 内容随 `schema_column_prune_enabled` /
        # `enum_hint_enabled` / `schema_asset_meta_enabled` / `recall_top_k` 等开关变化，
        # 只按「数据源|问题」缓存的话 —— 管理员刚改完开关，这边还在吐旧 prompt（最长 120 秒），
        # 表现就是"改了没反应"。eval 走 bypass_caches 不受影响，**线上**才会踩到。
        if not _svc._OBJECT_CTX.get() and not _svc._BYPASS_CACHE.get():
            key = f"{datasource or ''}|{question}|{_svc._cfg_sig(cfg)}|{_sig}"
            if len(_svc._SCHEMA_CTX_CACHE) >= _svc._SCHEMA_CTX_CACHE_MAX:
                for k in list(_svc._SCHEMA_CTX_CACHE)[: _svc._SCHEMA_CTX_CACHE_MAX // 5]:
                    _svc._SCHEMA_CTX_CACHE.pop(k, None)
            _svc._SCHEMA_CTX_CACHE[key] = (time.time(), ctx)
        return ctx
