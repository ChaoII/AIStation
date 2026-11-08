"""取数执行层：``_execute_one``（2026-11-08 从 service.py 拆出）。

**取数的唯一收口**：权限网关 → 字段级 ACL → 行列改写 → 执行 → 审计。四条路径
（ask / ask_stream / report / metric）都必须经过它，权限判定只在这里做一次。

跨模块依赖（``_execute_sql`` / ``_secure_ont_sql`` / ``_execute_custom_ds_sql`` /
``validate_sql`` / ``_legacy_check`` 等）仍留在 ``service.py``，这里通过
``from . import service as _svc`` 在**调用时**解析：导入期直接 import 会循环，
而延迟解析同时保证测试对 ``service._execute_sql`` 的 monkeypatch 继续生效。
"""
from __future__ import annotations

from app.core.exceptions import CustomException
from app.core.logger import log

from . import service as _svc


class ExecuteOps:
    @classmethod
    async def _execute_one(cls, sql: str, datasource: str, auth,
                          question: str = "", entry: str = "ask") -> dict:
        """**取数的唯一收口**（P0-3）：权限网关 → 字段级 ACL → 行/列改写 → 执行。

        四条路径（ask / ask_stream / report / metric）都必须经过这里：
        **权限判定只在本函数内做一次** —— P1 起统一交给 :func:`policy.guard.prepare`
        （星号止血 + 表级策略 + 审计 + shadow 差异），字段级 ACL
        （``_ont_sql_violations``）作为独立一层保留。
        修前它只挂在 ask/ask_stream 这条路上，报表与指标各自直连 ``_execute_sql``，
        于是「能问数就能造一条读敏感列的指标/报表模板并执行」——
        ``metrics/save`` / ``reports`` 与问数同权限码（``module_ai:query:ask``）。

        ``entry``：入口标记（ask/report/metric/export/eval/...），审计与 shadow 差异
        都用它；报表与指标已显式传 ``report`` / ``metric``，其余入口暂用默认 ``ask``
        （T8 起按入口逐个补齐）。

        **自定义数据源（``ds:{id}``）也走同一个网关**（旧判定换成它自己的
        ``_assert_ds_access``）：否则 ds:* 这条真实主链路整体绕过星号止血/主体校验/审计。
        差异只在两处，都与修前口径一致：
        - 字段级 ACL 仍由 ``_execute_custom_ds_sql`` 做（它按**外部库 schema** 校验）；
        - ``validate_sql`` 的系统表白名单不适用于外部库，故不进自定义源的 legacy_check。

        ``question`` 用于**软删除口径改写**（见 `softdelete` 模块）：给了问题、且
        问句不是在问"已删除"时，给业务表的 SQL 补 `"ISDELETED" = false`。
        为什么放在这里而不是提示词：实测提示词规则两轮自翻 5 题（baseline 0 题），
        收益 1~2 题还不如自身抖动；口径这种确定规则交给代码才稳定。
        """
        # ---- 权限唯一收口（P1）：QueryGuard.prepare -------------------------
        # 设计稿 §7/§10：所有问数入口的**权限判定**只走这一处，各入口只换 ``entry``。
        # 放在字段级 ACL **之前**：星号止血（P0）与表级策略必须先于列级判定生效，
        # 否则"旧判定放行的查询仍带着敏感星号过去"（见 guard 模块 docstring 第 2 条）。
        # enforce 下 guard 会返回**编译后的可执行 SQL**（``decision.sql``）：行过滤已
        # 下推、掩码已投影替换，执行时必须用它；legacy/shadow 为空（执行原 SQL）。
        from .policy import guard as _policy_guard
        from .policy.engine import Decision as _PolicyDecision
        from .policy.principal import load_principal as _load_principal

        principal = await _load_principal(auth, entry)

        if datasource and datasource != _svc.SYSTEM_DS:
            ds_id = int(datasource.split(":")[-1])
            if question and cls._cfg_bool(await cls._cfg(),
                                          "sql_softdelete_rewrite_enabled", True):
                sql = await cls._apply_softdelete_policy(question, sql, datasource)

            async def _legacy_ds_check() -> _PolicyDecision:
                """自定义源的旧判定：数据源角色授权（``_assert_ds_access``）。

                异常照旧上抛（无权限 → ``您无权限访问该数据源``），与修前文案一致。
                ``_execute_custom_ds_sql`` 里还会再查一次（幂等、只多一次短查询），
                那里不能省：enforce 模式下 guard 不会再调这个闭包。
                """
                await _svc._assert_ds_access(ds_id, auth)
                return _PolicyDecision(True, "legacy：数据源访问校验通过")

            # 三种模式都用**真实方言**：legacy 的星号止血（`unexpanded_star`）也要能
            # 解析 MySQL 反引号 / `# 注释` / FORCE INDEX，否则"能跑的查询"会被误杀。
            # `_sql_dialect` 有 300s 进程内缓存，成本可接受。
            decision = await _policy_guard.prepare(
                sql=sql,
                principal=principal,
                entry=entry,
                datasource=datasource,
                dialect=await cls._sql_dialect(datasource),
                legacy_check=_legacy_ds_check,
            )
            if not decision.permit:
                raise CustomException(msg=decision.reason)
            out = await _svc._execute_custom_ds_sql(ds_id, decision.sql or sql, auth)
            out["applied"] = [dict(a) for a in (decision.applied or ())]
            out["policy_ids"] = list(decision.policy_ids or ())
            return out

        # 复用本体的行级/列级权限：把本体对象支撑表改写成"已过滤的子查询"。
        # 问数是**任意形状的读**（聚合/分组/join），外面套 WHERE 是错的——
        # 过滤必须在聚合之前，所以这里做子查询改写。
        secured = await _svc._secure_ont_sql(sql, auth)
        if secured.get("deny"):
            raise CustomException(msg=secured["msg"])

        uid = getattr(getattr(auth, "user", None), "id", None)
        # legacy_check 已算过的字段级 ACL 结论；guard 之后复用，同一请求只查一次元数据。
        acl_violations: list[str] | None = None

        async def _legacy_check() -> _PolicyDecision:
            """旧校验组合：白名单（``validate_sql``）+ 字段级 ACL（``_ont_sql_violations``）。

            写成闭包（而不是先把结论算好再传）是为了**保持旧语义**：旧判定抛的
            ``CustomException`` 必须原样上抛 —— 具体文案与 fail-closed 收尾是前端、
            评测与既有用例依赖的；guard 的 ``_legacy_decision`` 正好不吞异常。
            """
            nonlocal acl_violations
            allowed = await cls._allowed_for_user(auth)
            _svc.validate_sql(sql, allowed)   # 只做校验，返回值不用（上游已规范化）
            try:
                acl_violations = await cls._ont_sql_violations(sql, uid)
            except Exception as e:  # noqa: BLE001
                log.warning(f"[query] 字段级 ACL 检查失败，拒绝执行：{e}")
                raise CustomException(
                    msg=f"字段级权限校验失败，已拒绝执行：{str(e)[:120]}") from e
            if acl_violations:
                return _PolicyDecision(
                    False,
                    f"字段级权限：无权限访问 {', '.join(acl_violations)}（本体属性级 ACL）")
            return _PolicyDecision(True, "legacy：白名单与字段级 ACL 均通过")

        decision = await _policy_guard.prepare(
            sql=sql,
            principal=principal,
            entry=entry,
            datasource=datasource or _svc.SYSTEM_DS,
            # I4：编译器输入 = 本体安全改写后的 SQL，产出直接执行（只 secure 一次）。
            # 这样执行 SQL 里同时含本体行过滤与策略行过滤，不会被二次改写覆盖。
            compile_sql=secured["sql"],
            legacy_check=_legacy_check,
        )
        if not decision.permit:
            raise CustomException(msg=decision.reason)

        # 字段级 ACL：仍是**独立一层**。legacy_check 算过就直接复用；``enforce`` 模式下
        # guard 不再执行旧判定（策略判定与编译改写由 guard 负责），这里必须补算 ——
        # 否则"切到新引擎"会把列级 ACL 丢掉，受限字段重新变成可读。
        # 安全补丁（2026-10-19）：必须在**共同执行出口**生效，且 fail-closed
        # （检查一炸就等于没做，受限字段会被原样查出来）。
        if acl_violations is None:
            try:
                acl_violations = await cls._ont_sql_violations(sql, uid)
            except Exception as e:  # noqa: BLE001
                log.warning(f"[query] 字段级 ACL 检查失败，拒绝执行：{e}")
                raise CustomException(
                    msg=f"字段级权限校验失败，已拒绝执行：{str(e)[:120]}") from e
        if acl_violations:
            raise CustomException(
                msg=f"字段级权限：无权限访问 {', '.join(acl_violations)}（本体属性级 ACL）")
        # P1-12 方案 b：内置默认敏感列名单（fail-closed 底板）——作为「配置显式标记」
        # （`ai_query_asset_columns.sensitive` / 本体属性 `sensitive`）之外的兜底，放在
        # 字段级 ACL **之后**：配置标记（业务明标敏感）优先报「字段级权限」；无标记但命中
        # 内置名单（如无人标注的明文凭据列）在此兜底拦截。
        # 用**原始 sql**（与 `_ont_sql_violations` 同源，不用改写后的 `secured["sql"]`）。
        # 对**所有用户（含超管）**生效：超管 `_ont_sql_violations` 会被 `_can_see_sensitive`
        # 短路返回空（不报「字段级权限」），但内置名单仍拦，确保敏感列永不返回。
        # 只拦「返回结果列」，不拦 WHERE / JOIN 引用。
        _default_hits = _svc._default_sensitive_return_cols(sql)
        if _default_hits:
            raise CustomException(
                msg=f"查询包含内置敏感列（默认拦截，永不返回）：{', '.join(_default_hits)}")
        # enforce：guard 的编译产物直接执行（本体过滤已在编译输入里，不再二次改写）。
        # I1：编译链路绕过了 `validate_sql`，这里补「只读/单语句/去注释/补 LIMIT」；
        # `allowed_tables=set()` 在 `validate_sql` 里等价于**跳过表白名单**
        # （`if allowed_lower and ...`），因此不会误杀策略允许的表。
        if decision.sql:
            out = await _svc._execute_sql(_svc.validate_sql(decision.sql, set()))
        else:
            out = await _svc._execute_sql(secured["sql"])
        # 供问数页「执行详情」展示：实际施加了哪些改写、命中哪些策略
        out["applied"] = [dict(a) for a in (decision.applied or ())]
        out["policy_ids"] = list(decision.policy_ids or ())
        return out
