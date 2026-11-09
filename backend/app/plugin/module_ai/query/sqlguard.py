"""SQL 校验：只读 / 单语句 / 白名单 / 补 LIMIT（2026-11-08 从 service.py 拆出）。

这是问数最后一道**静态**闸门：DML/DDL 一律拒绝，CTE 允许但体内藏 DML 也拒绝
（正则 + sqlglot AST 双层），白名单表大小写不敏感，最后兜一个 `LIMIT`。

``service.py`` 保留 ``validate_sql`` / ``_tables_in_sql`` 的再导出：调用方
（``agno_query_tools``、``nl2sql_ops``）与测试对 ``service.validate_sql`` 的
monkeypatch 都零改动。
"""
from __future__ import annotations

import re

from app.core.exceptions import CustomException

#: 禁止出现的语句关键字（DML/DDL/管理语句）
FORBIDDEN_RE = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|replace|merge|grant|revoke|"
    r"copy|vacuum|analyze|call|do|commit|rollback|savepoint|into|execute)\b",
    re.IGNORECASE,
)
#: SQL 注释（正则层先剥掉，避免 `-- ; drop` 之类绕过）
COMMENT_RE = re.compile(r"(--.*$)|(/\*.*?\*/)", re.MULTILINE | re.DOTALL)


def validate_sql(sql: str, allowed_tables: set[str], question: str = "") -> str:
    """校验并规范化 SQL：只读、单语句、白名单表、加 LIMIT。

    返回净化后的 SQL；不合法抛 CustomException。
    """
    if not sql or not sql.strip():
        raise CustomException(msg="未生成有效的查询语句")
    # 去除注释
    cleaned = COMMENT_RE.sub("", sql).strip()
    # 单语句
    removed_semis = cleaned.rstrip(";")
    if ";" in removed_semis:
        raise CustomException(msg="查询语句必须为单条 SELECT")
    # 只读：接受 SELECT 与 CTE（WITH ... SELECT）；其它语句一律拒。
    # 不能只看 `head.startswith("select")` —— `WITH x AS (...) SELECT ...` 是合法只读
    # 查询，enforce 补跑 validate 后会把整类 CTE 查询误杀（2026-11 复审回归）。
    # CTE 体内若藏 DML（`WITH x AS (DELETE ...) SELECT`）由下面的 `FORBIDDEN_RE`
    # 与 AST 的 DML 节点检查兜住。
    head = removed_semis.lstrip().lower()
    if re.match(r"^(select|with)\b", head) is None:
        raise CustomException(msg="仅允许 SELECT 查询")
    if FORBIDDEN_RE.search(removed_semis):
        raise CustomException(msg="查询包含被禁止的写/DDL 语句")
    # 白名单表（**大小写不敏感**：大小写敏感库里模型可能把小写名写出来，
    # 后面 quote_schema_identifiers 会还原成真名并加引号，所以这里放宽是安全的）
    from_src = re.findall(
        r"\bfrom\s+([A-Za-z_][A-Za-z0-9_\.]*)", removed_semis, re.IGNORECASE
    )
    allowed_lower = {str(t).lower() for t in allowed_tables} if allowed_tables else set()
    for tbl in from_src:
        base = tbl.split(".")[-1].strip().strip('"')
        if allowed_lower and base.lower() not in allowed_lower:
            raise CustomException(msg=f"表「{base}」不在可查询白名单内")
    # AST 级校验（sqlglot）：确保是合法且仅 SELECT 的单条语句
    try:
        import sqlglot
        from sqlglot import exp as sql_exp

        parsed = sqlglot.parse_one(removed_semis, read="postgres")
        if parsed is None:
            raise CustomException(msg="生成的 SQL 无法解析")
        # 任意位置出现写/DML 节点一律拒绝（容错过滤不存在的节点类）
        dml_nodes = [
            getattr(sql_exp, n, None)
            for n in ("Insert", "Update", "Delete", "Drop", "Create", "Alter", "Merge", "Grant")
        ]
        dml_nodes = [n for n in dml_nodes if n is not None]
        if any(parsed.find(n) for n in dml_nodes):
            raise CustomException(msg="查询包含被禁止的写/DDL 语句")
        if not parsed.find(sql_exp.Select):
            raise CustomException(msg="仅允许 SELECT 查询")
    except CustomException:
        raise
    except ImportError:
        pass  # 未安装 sqlglot 时跳过 AST 校验，交给正则层
    # 限制行数。
    # 这里还顺手修一类**确定性**的错：问题要"每个/各/所有"这类全量列举时，
    # 模型常自作主张加一个小 LIMIT（实测把 216 行截成 50 行，答案直接判错）。
    # 提示词里已经写了"不要 LIMIT"，但模型不总听——所以在这里兜住：
    # 放宽到系统上限（外层本来就有 _svc.MAX_ROWS 保护，放宽不会失控）。
    from . import service as _svc

    m_lim = re.search(r"\blimit\s+(\d+)", removed_semis, re.IGNORECASE)
    if not m_lim:
        removed_semis = removed_semis + f" LIMIT {_svc.MAX_ROWS}"
    elif _svc._wants_full_list(question) and int(m_lim.group(1)) < _svc.MAX_ROWS:
        removed_semis = re.sub(r"\blimit\s+\d+", f"LIMIT {_svc.MAX_ROWS}",
                               removed_semis, flags=re.IGNORECASE)
    return removed_semis


def tables_in_sql(sql: str) -> set[str]:
    """从指标 SQL 提取涉及的系统表（含 FROM/JOIN）。"""
    from . import service as _svc

    names = {
        m.group(1)
        for m in re.finditer(
            r"\b(?:from|join)\s+([A-Za-z_][A-Za-z0-9_]*)", sql or "", re.IGNORECASE
        )
    }
    return {n for n in names if n in _svc.SYSTEM_ALLOWED_TABLES}
