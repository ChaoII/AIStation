"""SQL / 检索缓存（2026-11-08 从 service.py 拆出）。

两个缓存都在**进程内**（dict + TTL），键里带数据源与配置指纹：
- SQL 缓存额外带**主体指纹**（``_auth_scope``）：不同用户不能复用同一份生成结果；
- 检索缓存必须带数据源，否则同一句话在两个源之间互相串结果。

缓存字典本身仍归 ``service.py``（``_SQL_CACHE`` / ``_RETRIEVAL_CACHE`` /
``_BYPASS_CACHE`` 等），这里用 ``_svc.`` 读取：测试里 ``S._SQL_CACHE.clear()``
与 ``monkeypatch.setattr(svc, "_RETRIEVAL_CACHE", {})`` 这类操作继续生效。
"""
from __future__ import annotations

import hashlib
import re
import time

from . import service as _svc


def sql_cache_key(question: str, datasource: str | None, scope: str = "") -> str:
    """归一化问题文本作为键（去空白、统一小写），避免大小写/空格差异漏命中。"""
    q = re.sub(r"\s+", "", (question or "").strip().lower())
    return f"{datasource or 'system'}::{q}::s:{scope}"


def sql_cache_get(question: str, datasource: str | None, scope: str = "") -> str | None:
    if _svc._BYPASS_CACHE.get():
        return None  # 评测：必须真的重新生成（见 _svc._BYPASS_CACHE 的说明）
    key = sql_cache_key(question, datasource, scope)
    hit = _svc._SQL_CACHE.get(key)
    if not hit:
        return None
    ts, sql = hit
    if time.time() - ts > _svc._SQL_CACHE_TTL:
        _svc._SQL_CACHE.pop(key, None)
        return None
    return sql


def sql_cache_set(question: str, datasource: str | None, sql: str, scope: str = "") -> None:
    if _svc._BYPASS_CACHE.get():
        return  # 评测生成的 SQL 不得污染真实用户的缓存
    if not sql or not sql.strip():
        return
    if len(_svc._SQL_CACHE) >= _svc._SQL_CACHE_MAX:
        # 简单淘汰：删最早插入的一批，避免引入额外依赖
        for k in list(_svc._SQL_CACHE)[: max(1, _svc._SQL_CACHE_MAX // 10)]:
            _svc._SQL_CACHE.pop(k, None)
    _svc._SQL_CACHE[sql_cache_key(question, datasource, scope)] = (time.time(), sql)


def sql_cache_clear() -> int:
    n = len(_svc._SQL_CACHE)
    _svc._SQL_CACHE.clear()
    return n


def retrieval_cache_key(question: str, datasource: str | None = None) -> str:
    """检索缓存 key：**必须含数据源** —— 否则同一句话在两个数据源之间互相串结果
    （实测 ds:4 的问题会命中 system 源的缓存，召回到 video_*/ai_* 表）。"""
    q = re.sub(r"\s+", "", (question or "").strip().lower())
    return f"{datasource or ''}|{q}"


def cfg_sig(cfg: dict | None) -> str:
    """配置指纹：只取影响召回/prompt 的那些 key，算一个短哈希。

    为什么不用「保存设置时清缓存」：那是**进程内**的，多进程/多副本部署时只有
    接住这次保存的那个进程会清，其它进程照旧吐旧结果 —— 这类"偶发"最难查。
    把指纹拼进 cache key 是确定性的，和有多少个进程无关。
    """
    cfg = cfg or {}
    raw = "|".join(f"{k}={cfg.get(k)}" for k in _svc._CTX_CFG_KEYS)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]
