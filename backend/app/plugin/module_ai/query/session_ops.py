"""会话与消息：历史、落库、反馈（2026-11-08 从 service.py 拆出）。

- 会话归属：``list_sessions`` / ``_ensure_session_owner`` 只允许看本人的（历史遗留
  ``user_id`` 为空的行除外），否则会出现「能看到别人标题、点进去却说会话不存在」；
- 评测会话（``is_eval``）默认不进历史，否则题库会把真实列表刷屏（实测同一题 85 次）；
- ``feedback``：反馈正例可沉淀为 few-shot，但 SQL 必须先过 ``validate_sql``。

``_actor_id`` / ``_system_allowed`` / ``SYSTEM_DS`` / ``_EVAL_CTX`` 等仍归
``service.py``，这里用 ``_svc.`` 在调用时解析。
"""
from __future__ import annotations

from app.core.database import async_db_session
from app.core.exceptions import CustomException

from . import service as _svc
from .model import AiQueryFewshotModel, AiQueryMessageModel, AiQuerySessionModel


class SessionOps:
    @classmethod
    async def _ensure_favorite_table(cls, db) -> None:
        from sqlalchemy import text as _t
        dialect = (db.bind.dialect.name if db.bind else "")
        if dialect == "postgresql":
            await db.execute(_t(
                "CREATE TABLE IF NOT EXISTS ai_favorite ("
                "id BIGSERIAL PRIMARY KEY, kind VARCHAR(64), ref VARCHAR(255), "
                "user_id INTEGER, is_deleted INTEGER DEFAULT 0, created_time TIMESTAMP)"))
        else:
            await db.execute(_t(
                "CREATE TABLE IF NOT EXISTS ai_favorite ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, ref TEXT, "
                "user_id INTEGER, is_deleted INTEGER DEFAULT 0, created_time TEXT)"))

    @classmethod
    async def favorites_list(cls, user_id: int = 0) -> list[dict]:
        async with async_db_session.begin() as db:
            await cls._ensure_favorite_table(db)
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            rows = (await db.execute(_t(
                "SELECT id,kind,ref,created_time FROM ai_favorite WHERE is_deleted=0 AND user_id=:u ORDER BY id DESC"),
                {"u": user_id})).fetchall()
        return [{"id": r[0], "kind": r[1], "ref": r[2], "time": str(r[3]) if r[3] else ""} for r in rows]

    @classmethod
    async def favorites_add(cls, kind: str, ref: str, user_id: int = 0) -> dict:
        from datetime import datetime
        async with async_db_session.begin() as db:
            await cls._ensure_favorite_table(db)
            from sqlalchemy import text as _t
            ex = (await db.execute(_t(
                "SELECT id FROM ai_favorite WHERE kind=:k AND ref=:r AND user_id=:u AND is_deleted=0"),
                {"k": kind, "r": ref, "u": user_id})).fetchone()
            if ex:
                return {"ok": True, "msg": "已收藏"}
            await db.execute(_t(
                "INSERT INTO ai_favorite(kind,ref,user_id,created_time) VALUES (:k,:r,:u,:now)"),
                {"k": kind, "r": ref, "u": user_id,
                 "now": datetime.now()})
        return {"ok": True, "msg": "收藏成功"}

    @classmethod
    async def favorites_remove(cls, fav_id: int, user_id: int = 0) -> dict:
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t
            await db.execute(_t(
                # ai_favorite.is_deleted 是 **integer**（建表语句与线上库都是），
                    # 这里原来写 `is_deleted=true`：SQLite 能容忍，PG 报
                    # "operator does not exist: integer = boolean"（取消收藏直接失败）。
                    "UPDATE ai_favorite SET is_deleted=1 WHERE id=:i AND user_id=:u"),
                {"i": fav_id, "u": user_id})
        return {"ok": True, "msg": "已取消收藏"}

    @classmethod
    async def get_or_create_session(cls, session_id: int | None, title: str, auth) -> dict:
        async with async_db_session.begin() as db:
            if session_id:
                s = await db.get(AiQuerySessionModel, session_id)
                if s:
                    # 命中已有会话时必须校验归属：`ask`/`ask_stream` 会拿着这个 id
                    # 继续写消息，旧实现不校验 → 可把消息写进他人会话。
                    cls._ensure_session_owner(s, auth)
                    return {"id": s.id, "title": s.title, "datasource": s.datasource}
            user = getattr(getattr(auth, "user", None), "id", None)
            s = AiQuerySessionModel(
                user_id=user, tenant_id=None, title=title[:60] or "新会话",
                datasource=_svc.SYSTEM_DS, created_id=user, updated_id=user,
                is_eval=_svc._EVAL_CTX.get(),
            )
            db.add(s)
            await db.flush()
            return {"id": s.id, "title": s.title, "datasource": s.datasource}

    @classmethod
    async def list_sessions(cls, auth, include_eval: bool = False) -> list[dict]:
        async with async_db_session() as db:
            from sqlalchemy import or_, select

            conds = [AiQuerySessionModel.is_deleted.is_(False)]
            if not include_eval:
                # 评测会话默认不进问数历史（题库的题会把真实历史刷屏：实测同一题重复 85 次）
                conds.append(or_(AiQuerySessionModel.is_eval.is_(False),
                                 AiQuerySessionModel.is_eval.is_(None)))
            uid = _svc._actor_id(auth)
            if uid is not None:
                # 与 `_ensure_session_owner` 同口径：本人 + 历史遗留（user_id 为 NULL）。
                # 旧实现完全不按用户过滤 → 所有人能看到所有人的会话标题，
                # 点进去 `list_messages` 却报"会话不存在"（自相矛盾，且泄露标题）。
                conds.append(
                    or_(AiQuerySessionModel.user_id == uid,
                        AiQuerySessionModel.user_id.is_(None))
                )
            rows = (
                await db.execute(
                    select(AiQuerySessionModel)
                    .where(*conds)
                    .order_by(AiQuerySessionModel.id.desc())
                    .limit(100)
                )
            ).scalars().all()
            return [
                {"id": s.id, "title": s.title, "datasource": s.datasource,
                 "created_time": s.created_time}
                for s in rows
            ]

    @classmethod
    def _ensure_session_owner(cls, sess: AiQuerySessionModel | None, auth) -> None:
        """会话归属校验。

        修复前 `list_messages` / `delete_session` **只按 id 查**，任何拿到
        ``module_ai:query:ask`` 权限的用户都能按 id 读到、删掉**别人的**问数历史
        （枚举 id 即可越权）。这里统一校验：归属人必须是当前用户；
        报「不存在」而不是「无权限」，避免暴露 id 的存在性。
        """
        if sess is None:
            raise CustomException(msg="会话不存在")
        if auth is None:
            return  # 内部调用（如问句重写读历史）无 HTTP 用户上下文；HTTP 边界一律传 auth
        owner = getattr(sess, "user_id", None)
        if owner is None:
            return  # 历史遗留数据（无归属），保持可访问
        uid = getattr(getattr(auth, "user", None), "id", None)
        if uid is None or int(owner) != int(uid):
            raise CustomException(msg="会话不存在")

    @classmethod
    async def list_messages(cls, session_id: int, auth=None) -> list[dict]:
        async with async_db_session() as db:
            from sqlalchemy import select

            cls._ensure_session_owner(await db.get(AiQuerySessionModel, session_id), auth)
            rows = (
                await db.execute(
                    select(AiQueryMessageModel)
                    .where(
                        AiQueryMessageModel.session_id == session_id,
                        AiQueryMessageModel.is_deleted.is_(False),
                    )
                    .order_by(AiQueryMessageModel.id)
                )
            ).scalars().all()
            return [cls._msg_dict(m) for m in rows]

    @classmethod
    async def delete_session(cls, session_id: int, auth=None) -> None:
        async with async_db_session.begin() as db:
            s = await db.get(AiQuerySessionModel, session_id)
            if s is None:
                return  # 已不存在：保持幂等，不因重复删除而报错
            cls._ensure_session_owner(s, auth)
            await db.delete(s)

    @classmethod
    async def _save_message(cls, session_id: int, question: str, **kw) -> AiQueryMessageModel:
        async with async_db_session.begin() as db:
            m = AiQueryMessageModel(
                session_id=session_id, question=question,
                path=kw.get("path", "fast"), datasource=kw.get("datasource", _svc.SYSTEM_DS),
                sql=kw.get("sql", ""), columns=kw.get("columns") or [],
                rows=kw.get("rows") or [], summary=kw.get("summary", ""),
                result_rows=kw.get("result_rows", 0), took_ms=kw.get("took_ms", 0),
                cached=kw.get("cached", False), usage=kw.get("usage"),
                is_error=kw.get("is_error", False),
                grounding=kw.get("grounding"),
            )
            db.add(m)
            await db.flush()
            return m

    @classmethod
    async def feedback(cls, message_id: int, feedback: str, correct_sql: str | None, auth) -> dict:
        import uuid as _uuid

        from sqlalchemy import select as _sel

        async with async_db_session.begin() as db:
            m = await db.get(AiQueryMessageModel, message_id)
            if not m:
                raise CustomException(msg="记录不存在")
            # 归属校验：旧实现只按 message_id 取行 → 谁都能改他人反馈，
            # 还能把他人问答沉淀成自己的 few-shot。按 session_id 反查会话统一校验。
            cls._ensure_session_owner(
                await db.get(AiQuerySessionModel, m.session_id), auth)
            m.feedback = feedback
            m.updated_id = auth.user.id
            sunk = False
            reason = ""
            if correct_sql:
                # ① **先存下来**：人工修正的 SQL 本身就是最宝贵的样本，
                #    绝不能因为"没通过校验/沉淀失败"就丢掉（旧实现在这里 return，直接丢了）
                m.correct_sql = correct_sql
                # ② 再尝试沉淀成 few-shot：按**该消息的数据源**校验
                #    （旧实现永远用系统白名单 → ds:4 的修正 SQL 一律被判非法）
                if cls._cfg_bool(await cls._cfg(), "fewshot_auto_curate", True):
                    try:
                        if (m.datasource or _svc.SYSTEM_DS) == _svc.SYSTEM_DS:
                            _svc.validate_sql(correct_sql, await _svc._system_allowed())
                        else:
                            _ds_id = int(str(m.datasource).split(":")[-1])
                            _rows = await _svc.list_ds_schema(_ds_id, included_only=True)
                            _svc.validate_sql(correct_sql, {r["table"] for r in _rows})
                    except Exception as e:  # noqa: BLE001
                        reason = f"SQL 未通过校验，已保存但未沉淀：{getattr(e, 'msg', e)}"
                    else:
                        exists = (
                            await db.execute(
                                _sel(AiQueryFewshotModel).where(
                                    AiQueryFewshotModel.question == m.question,
                                    AiQueryFewshotModel.is_deleted.is_(False),
                                )
                            )
                        ).scalar_one_or_none()
                        if not exists:
                            # ⚠️ uuid/status 是 NOT NULL：旧实现没赋值 →
                            #    插入报错 → **整个事务回滚** → 连反馈都存不下（实测 0 条反馈的真因之一）
                            db.add(
                                AiQueryFewshotModel(
                                    datasource=m.datasource, question=m.question,
                                    sql=correct_sql, enabled=True, status="0",
                                    uuid=_uuid.uuid4().hex,
                                    created_id=auth.user.id, updated_id=auth.user.id,
                                )
                            )
                            sunk = True
            await db.flush()
            return {"id": m.id, "feedback": feedback, "sunk": sunk, "reason": reason}
