"""AI 工作台服务：分类树 CRUD + 多类型条目聚合。"""
from __future__ import annotations

import time as _time
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.logger import log
from app.utils.common_util import traversal_to_tree
from app.utils.trigger_util import TriggerUtil

from .model import AiWorkspaceCategoryModel, AiWorkspaceCronModel

#: 可聚合的类型 → (本模块模型, 名称字段, 中文名)。
#: agent/workflow/app 的表**不在这里**——它们由各模块的 list_* 接口取数（见 items()）；
#: 这里只留本模块自己的 cron 表。
_TYPES = {
    "cron": (AiWorkspaceCronModel, "name", "定时任务"),
}
#: 全部可聚合类型（跨模块的三种 + 本模块的 cron）
ALL_TYPES = ("agent", "workflow", "app", "cron")

#: 类型默认图标（Element Plus 图标组件名；条目未设 icon/avatar 或设为非图片图标时用于卡片展示）
_TYPE_ICON = {
    "agent": "User",
    "workflow": "Connection",
    "app": "Monitor",
    "cron": "Timer",
}


#: 启用中的定时任务必须有触发表达式：空表达式 = 「已启用但永不触发」的静默失效，
#: 用户看不到任何提示。三处写入路径（工作台 / 工作流 / 训练）口径必须一致。
_EMPTY_TRIGGER_MSG = "请先配置触发时间（分 时 日 月 周）"

#: 本模块在中心调度器里的作业键前缀（与 `ap_scheduler._BUSINESS_JOB_PREFIXES` 同口径）：
#: 三个模块共用一个调度器，作业键必须带自己的前缀，同步时也只能清理自己的前缀范围
#: （否则会把别的模块的定时任务一并删掉——无告警、只在下次触发时表现为「任务不再运行」）。
_JOB_PREFIX = "ai_workspace_cron:"

#: 调度（无用户输入）运行时使用的固定消息：agent 的 guardrail 拒绝空输入，
#: 且「定时执行」语义就是「按配置跑一次」，不引入第二套输入契约。
_SCHEDULE_MESSAGES: list[dict] = [{"role": "user", "content": "按你的配置执行"}]


def _job_key(cron_id: int) -> str:
    """本模块在中心调度器里的作业键（`ai_workspace_cron:{id}`）。"""
    return f"{_JOB_PREFIX}{cron_id}"


def _is_image_icon(icon: str) -> bool:
    """判断图标是否为图片路径（http(s)/图片扩展名/agent-icons 等），非图片则用类型默认图标。"""
    i = (icon or "").strip()
    return bool(
        i
        and (
            i.startswith("http://")
            or i.startswith("https://")
            or i.endswith((".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif"))
            or i.startswith("market-icons/")
            or i.startswith("agent-icons/")
        )
    )


def _tool_detail(tool: dict) -> str:
    """把一次工具调用摊平成可读文本（参数 + 结果），卡片里展开看。"""
    import json as _json

    def _fmt(v, limit: int) -> str:
        if v is None:
            return "—"
        if isinstance(v, str):
            s0 = v
        else:
            try:
                s0 = _json.dumps(v, ensure_ascii=False)
            except Exception:  # noqa: BLE001
                s0 = str(v)
        s0 = " ".join(s0.split())
        return s0 if len(s0) <= limit else s0[:limit] + "…"

    args = _fmt(tool.get("args"), 400)
    result = _fmt(tool.get("result"), 800)
    return f"参数：{args}\n结果：{result}"


async def _notify_cron_auto_disabled(
    cron_id: int, cron_name: str, streak: int, reason: str
) -> None:
    """定时任务被自动停用 → 给管理员发通知（best-effort，通道没配就静默跳过）。

    - 开关：系统参数 ``ai_cron_notify_channels``（``email,webhook``，空=关闭）；
    - 凭证/收件人沿用告警模块的通用参数：``notify_admin_email``、
      ``notify_webhook_default_url``（管理员邮箱 / 默认 Webhook），
      所以管理员不用再单独配一套；
    - 任何失败只记 warning，不影响任务状态回写。
    """
    from app.utils.notification import _send_email, _send_webhook, load_params

    try:
        async with async_db_session() as db:
            params = await load_params(
                db,
                "ai_cron_notify_channels",
                "notify_admin_email",
                "notify_webhook_default_url",
            )
            want = [
                c.strip().lower()
                for c in (params.get("ai_cron_notify_channels") or "").split(",")
                if c.strip()
            ]
            if not want:
                return
            ready: list[str] = []
            if "email" in want and (params.get("notify_admin_email") or "").strip():
                ready.append("email")
            if "webhook" in want and (params.get("notify_webhook_default_url") or "").strip():
                ready.append("webhook")
            if not ready:
                log.info(
                    "[cron] 自动停用通知已开启，但管理员邮箱 / 默认 Webhook 都没配，跳过"
                )
                return

            now = datetime.now()
            alarm = {
                "alarm_type": "定时任务自动停用",
                "severity": "WARNING",
                "description": (
                    f"定时任务「{cron_name}」(#{cron_id}) 连续失败 {streak} 次，已自动停用。"
                    f"最近一次错误：{(reason or '').strip()[:300]}"
                ),
                "alarm_time": str(now),
                "camera_name": "AIStation 定时任务",
                "camera_id": "",
                "rule_id": cron_id,
                "rule_name": "定时任务连续失败保护",
                "snapshot_path": "",
            }
            rule = {
                "id": cron_id,
                "name": "定时任务连续失败保护",
                "notify_channels": ready,
            }
            senders = {"email": _send_email, "webhook": _send_webhook}
            for channel in ready:
                try:
                    await senders[channel](db, alarm, rule, {})
                    log.info(f"[cron] 自动停用通知已发送（{channel}）：#{cron_id}")
                except Exception as e:  # noqa: BLE001 单通道失败不影响其它通道
                    log.warning(
                        f"[cron] 自动停用通知（{channel}）发送失败：{str(e)[:120]}"
                    )
    except Exception as e:  # noqa: BLE001 通知是附加动作，绝不能影响主流程
        log.warning(f"[cron] 自动停用通知失败（忽略）：{str(e)[:120]}")


# 正在跑的定时任务（进程内闸门）：同一个任务不允许并发跑两遍。
# 调度器的 max_instances 只管它自己发起的作业，"立即执行"是另一条入口，
# 连点两下 / 上一轮还没跑完又到点，都会真的跑两遍（实测复现过）。
# 值 = 开始时间（monotonic）：万一某轮卡死不返回，超过阈值就把记录放掉，
# 否则这个任务会被永远锁死（接口一直回"上一轮还在执行"）。
_RUNNING_CRONS: dict[int, float] = {}
_CRON_LOCK_STALE_SEC = 30 * 60
# 连续失败到这个次数就自动停用（避免坏配置一直烧模型调用）
_CRON_FAIL_STREAK_LIMIT = 3


def cron_is_running(cron_id: int) -> bool:
    """这个定时任务当前是不是正在跑（给接口回话用）。"""
    started = _RUNNING_CRONS.get(cron_id)
    if started is None:
        return False
    if _time.monotonic() - started > _CRON_LOCK_STALE_SEC:
        log.warning(f"[cron] 定时任务 #{cron_id} 的执行记录超过 30 分钟，按卡死处理并解锁")
        _RUNNING_CRONS.pop(cron_id, None)
        return False
    return True


async def run_scheduled_workspace_cron(cron_id: int) -> None:
    """中心调度器作业入口：同一任务串行执行（正在跑就跳过这一轮）。

    真正的执行体在 `_run_cron_once`。这里的闸门是进程内的：单实例部署够用，
    多实例部署需要换成 Redis 锁（当前项目是单进程 + APScheduler）。
    """
    if cron_is_running(cron_id):
        log.warning(f"[cron] 定时任务 #{cron_id} 上一轮还没跑完，跳过这一轮")
        return
    _RUNNING_CRONS[cron_id] = _time.monotonic()
    try:
        await _run_cron_once(cron_id)
    finally:
        _RUNNING_CRONS.pop(cron_id, None)


async def _run_cron_once(cron_id: int) -> None:
    """执行工作台定时任务绑定的资产，并回写运行状态。

    刻意用**模块级函数**（而非闭包）：`obj_to_ref` 能解析出引用，作业状态可完整序列化，
    日志里也有可读的函数名（闭包会走降级路径）。

    作业与库里的行之间存在窗口期（禁用/删除/改表达式后作业可能还没来得及移除），
    因此触发时**以库为准**重新判定：行不存在、已删除、已禁用都直接跳过；
    **未配置触发表达式也跳过，但 `now`（立即执行）例外** —— 它按契约本就没有参数
    （`trigger_args` 恒为 `NULL`），不是「未配置」；漏掉这个例外，A9 注册上的一次性作业
    触发时会被再次拦下，作业空转。
    `next_run_time` 一律由作业回写（单一真源）：运行结束后（无论成败）从作业读回，
    库里的值永远等于作业的值，业务侧不再自算。
    """
    started = datetime.now(ZoneInfo(TriggerUtil.TIMEZONE))
    async with async_db_session() as db:
        row = await db.get(AiWorkspaceCronModel, cron_id)
        if (
            not row
            or row.is_deleted
            or not row.enabled
            or not (row.trigger_args or row.trigger == "now")
        ):
            return
        target_type, target_id = row.target_type, row.target_id
        # 会话一关属性就过期，名字必须在会话内取出来
        cron_name = (row.name or "").strip() or f"定时任务#{cron_id}"
    # 定时任务也要进「AI 办公室」的任务列表和执行过程：
    # 以前只写 ai_call_logs，办公室只能看到一个 cron 计数，看不到谁在干什么。
    import time as _t
    import uuid as _uuid

    from app.plugin.module_ai.logs_center import run_steps as _rs

    run_id = _uuid.uuid4().hex
    seq = {"n": 0}
    agent_id, agent_name = None, cron_name
    if target_type == "agent" and target_id:
        # 目标是人：把名字查出来，办公室才能让这个人真的动起来
        agent_id = int(target_id)
        try:
            from app.plugin.module_ai.agent.service import AiAgentService

            ag = await AiAgentService.get_agent(agent_id)
            if ag and ag.get("agent_name"):
                agent_name = ag["agent_name"]
        except Exception as exc:  # noqa: BLE001
            log.warning(f"[cron] 查智能体名字失败：{exc}")

    async def _step(
        kind: str, title: str, detail: str | None = None, ok: bool = True, ms: int = 0
    ):
        try:
            await _rs.add(run_id, seq["n"], kind, title, agent_id, agent_name, detail, ms, ok)
            seq["n"] += 1
        except Exception as exc:  # noqa: BLE001
            log.warning(f"[cron] 写执行步骤失败：{exc}")

    await _step("plan", f"定时任务：{cron_name}", detail=f"定时任务：{cron_name}")
    t0 = _t.perf_counter()
    last_status, last_ms, last_msg = "success", 0, ""

    async def _attempt() -> tuple[str, str | None, list[dict]]:
        text, err, tools = await WorkspaceService._run_target(target_type, target_id)
        # 工具调用明细也进时间线（卡片「过程」里可以展开看参数/结果）
        for tl in tools or []:
            await _step(
                "tool",
                str(tl.get("name") or "工具"),
                detail=_tool_detail(tl),
                ok=bool(tl.get("ok", True)),
                ms=int(tl.get("ms") or 0),
            )
        return text, err, tools

    try:
        text, run_err, _tools = await _attempt()
        if run_err:
            # 流里发的是 RunError（智能体被禁用 / 模型报错…）：不能记成成功
            raise RuntimeError(run_err)
        spent = int((_t.perf_counter() - t0) * 1000)
        last_ms, last_msg = spent, (text or "")
        await _step(
            "summary", "定时任务执行完成",
            detail=f"{cron_name} 已执行，耗时 {spent} ms",
            ms=spent,
        )
    except Exception as exc:  # noqa: BLE001 单次执行失败不抛出，避免污染作业状态
        first_err = str(exc)[:300]
        log.warning(f"工作台定时任务 #{cron_id} 第 1 次失败，自动重试一次：{first_err}")
        await _step(
            "retry", "第 1 次失败，自动重试一次", detail=first_err, ok=False,
            ms=int((_t.perf_counter() - t0) * 1000),
        )
        # 给模型/网络一点恢复时间再试，避免瞬时抖动直接记成失败
        import asyncio as _aio

        await _aio.sleep(2)
        try:
            text2, err2, _t2 = await _attempt()
            if err2:
                raise RuntimeError(err2)
            spent = int((_t.perf_counter() - t0) * 1000)
            last_ms, last_msg = spent, (text2 or "")
            await _step(
                "summary", "重试后执行完成",
                detail=f"{cron_name} 重试后成功，总耗时 {spent} ms",
                ms=spent,
            )
        except Exception as exc2:  # noqa: BLE001 重试仍失败：记最终失败
            log.error(f"工作台定时任务 #{cron_id} 重试后仍失败：{exc2}")
            last_status = "error"
            last_ms = int((_t.perf_counter() - t0) * 1000)
            last_msg = f"重试后仍失败：{str(exc2)[:280]}"
            await _step(
                "error", "重试后仍失败",
                detail=last_msg, ok=False, ms=last_ms,
            )
    finally:
        # 执行历史也落 ai_call_logs（usage=cron + app_id=cron_id）：
        # 卡片上的「执行历史」列表读这里；办公室的执行过程读 ai_run_steps，两者互补。
        try:
            from app.plugin.module_ai.overview.service import AiOverviewService

            await AiOverviewService.add_log(
                cron_name,
                "cron",
                last_ms,
                last_status,
                None if last_status == "success" else last_msg,
                app_id=cron_id,
                user_id=None,
                reply_preview=(last_msg or None) if last_status == "success" else None,
            )
        except Exception as log_exc:  # noqa: BLE001 历史写入失败不应影响作业
            log.warning(f"定时任务执行历史写入失败：{str(log_exc)[:120]}")
        # 只有真正执行过的这一轮才回写 `last_run_time`（被跳过的行不记「刚跑过」）；
        # 结果也一起落库，卡片上直接看得到，不用再翻调用日志。
        await WorkspaceService.write_back_cron_state(
            cron_id,
            ran_at=started,
            status=last_status,
            duration_ms=last_ms,
            message=last_msg,
            run_id=run_id,
        )


class WorkspaceService:

    # ---------- 分类 ----------

    @classmethod
    async def list_tree(cls) -> list[dict]:
        """返回分类树（多级）。"""
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiWorkspaceCategoryModel).where(
                        AiWorkspaceCategoryModel.is_deleted.is_(False)
                    ).order_by(AiWorkspaceCategoryModel.sort.asc(), AiWorkspaceCategoryModel.id.asc())
                )
            ).scalars().all()
            flat = [
                {
                    "id": c.id,
                    "name": c.name,
                    "parent_id": c.parent_id,
                    "icon": c.icon or "",
                    "color": c.color or "",
                    "sort": c.sort or 0,
                }
                for c in rows
            ]
            return traversal_to_tree(flat)

    @classmethod
    async def create_category(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            if data.parent_id:
                parent = await db.get(AiWorkspaceCategoryModel, data.parent_id)
                if not parent or parent.is_deleted:
                    raise CustomException(msg="父分类不存在")
            row = AiWorkspaceCategoryModel(
                name=data.name,
                parent_id=data.parent_id,
                icon=data.icon or "",
                color=data.color or "",
                sort=data.sort or 0,
                created_id=auth.user.id,
                updated_id=auth.user.id,
            )
            db.add(row)
            await db.flush()
            return {"id": row.id, "name": row.name}

    @classmethod
    async def update_category(cls, cat_id: int, data, auth) -> dict | None:
        async with async_db_session.begin() as db:
            row = await db.get(AiWorkspaceCategoryModel, cat_id)
            if not row or row.is_deleted:
                return None
            for key in ("name", "icon", "color", "sort"):
                val = getattr(data, key, None)
                if val is not None:
                    setattr(row, key, val)
            row.updated_id = auth.user.id
            await db.flush()
            return {"id": row.id, "name": row.name}

    @classmethod
    async def delete_category(cls, cat_id: int, auth) -> None:
        async with async_db_session.begin() as db:
            row = await db.get(AiWorkspaceCategoryModel, cat_id)
            if not row or row.is_deleted:
                raise CustomException(msg="分类不存在")
            # 子分类的 parent_id 由 FK SET NULL 置空；条目 category_id 同理
            await db.delete(row)

    # ---------- 聚合条目 ----------

    @classmethod
    async def items(cls, category_id: int | None = None, asset_type: str | None = None) -> dict:
        """按分类/全部聚合 agent/workflow/app/cron 为统一条目。

        跨模块取数走**各模块自己的接口**（``list_agents`` / ``list_workflows`` / ``list_apps``），
        不直读它们的表；分类与启用过滤在本模块内做（条目量小，不值得给 owner 加过滤参数）。
        ``cron`` 是本模块自己的表，保持直读。
        """
        from app.plugin.module_ai.agent.service import AiAgentService
        from app.plugin.module_ai.apps.service import AiAppService
        from app.plugin.module_ai.workflow.service import AiWorkflowService

        if asset_type and asset_type not in ALL_TYPES:
            raise CustomException(msg=f"不支持的条目类型：{asset_type}")
        #: 跨模块类型 → (取数接口, 名称字段, 中文名)
        cross = {
            "agent": (AiAgentService.list_agents, "agent_name", "智能体"),
            "workflow": (AiWorkflowService.list_workflows, "name", "工作流"),
            "app": (AiAppService.list_apps, "name", "应用"),
        }
        async with async_db_session() as db:
            # 若选中父分类，则包含其所有后代分类
            cat_ids = None
            if category_id:
                cat_ids = await cls._descendant_ids(db, category_id)
            out: list[dict] = []
            for kind in ALL_TYPES:
                if asset_type and asset_type != kind:
                    continue
                if kind == "cron":  # 本模块自己的表
                    model, name_field, label = _TYPES[kind]
                    rows = (
                        await db.execute(select(model).where(model.is_deleted.is_(False)))
                    ).scalars().all()
                    out.extend(cls._to_item(kind, r, label, name_field) for r in rows)
                    continue
                fetch, name_field, label = cross[kind]
                for r in await fetch():
                    if not r.get("enabled", True):
                        continue
                    if cat_ids is not None and r.get("category_id") not in cat_ids:
                        continue
                    out.append(cls._to_item(kind, r, label, name_field))
            out.sort(key=lambda x: (x["category_id"] or 0, x["id"] or 0))
            return {"total": len(out), "items": out}

    @classmethod
    async def _descendant_ids(cls, db, root_id: int) -> set[int]:
        """收集 root 及其所有后代分类 id。"""
        all_rows = (
            await db.execute(
                select(AiWorkspaceCategoryModel.id, AiWorkspaceCategoryModel.parent_id)
            )
        ).all()
        children: dict[int | None, list[int]] = {}
        for cid, pid in all_rows:
            children.setdefault(pid, []).append(cid)
        ids: set[int] = {root_id}
        stack = [root_id]
        while stack:
            cur = stack.pop()
            for child in children.get(cur, []):
                if child not in ids:
                    ids.add(child)
                    stack.append(child)
        return ids

    @staticmethod
    def _g(row, key: str, default=None):
        """条目取值：他模块接口返回 **dict**，本模块 cron 是 **ORM 行**，统一取值。"""
        if isinstance(row, dict):
            v = row.get(key, default)
        else:
            v = getattr(row, key, default)
        return default if v is None else v

    @classmethod
    def _to_item(cls, kind: str, row, label: str, name_field: str) -> dict:
        icon = cls._g(row, "icon", "") or cls._g(row, "avatar", "")
        if not _is_image_icon(icon):
            icon = _TYPE_ICON.get(kind, icon or "")
        base = {
            "type": kind,
            "id": cls._g(row, "id"),
            "name": cls._g(row, name_field, "") or "",
            "description": cls._g(row, "description", "") or "",
            "enabled": bool(cls._g(row, "enabled", True)),
            "icon": icon,
            "color": cls._g(row, "color", "") or "",
            "category_id": cls._g(row, "category_id"),
            "label": label,
            "created_time": cls._g(row, "created_time"),
        }
        # 类型专属元信息（供卡片展示更饱满）
        if kind == "agent":
            meta = {
                "role": cls._g(row, "agent_role", "") or "",
                "model_id": cls._g(row, "model_id"),
                "tools": len(cls._g(row, "tool_ids", []) or []),
                "skills": len(cls._g(row, "skill_ids", []) or []),
                "mcp": len(cls._g(row, "mcp_ids", []) or []),
                "knowledge": len(cls._g(row, "knowledge_ids", []) or []),
            }
        elif kind == "workflow":
            graph = cls._g(row, "graph", {}) or {}
            meta = {"nodes": len(graph.get("nodes", []) or [])}
        elif kind == "app":
            meta = {
                "model_id": cls._g(row, "model_id"),
                "tools": len(cls._g(row, "tools", []) or []),
                "app_type": cls._g(row, "app_type", "") or "",
                "output_format": cls._g(row, "output_format", "") or "",
            }
        else:  # cron
            meta = {
                "cron": cls._g(row, "trigger_args", "") or "",
                # 与 `/cron/list` 同口径：人话描述（聚合条目同样优先展示它）
                "trigger_describe": TriggerUtil.describe_args(
                    cls._g(row, "trigger", "cron") or "cron", cls._g(row, "trigger_args", None)
                ),
                "target_type": cls._g(row, "target_type", "") or "",
                # 时间统一走 `to_local_str`：timestamptz 经 asyncpg 读回是 UTC，直接格式化会早 8 小时
                "next_run_time": TriggerUtil.to_local_str(cls._g(row, "next_run_time")),
            }
        base["meta"] = meta
        return base

    # ---------- 定时任务条目 ----------

    @classmethod
    async def list_cron(cls, category_id: int | None = None, target_type: str | None = None) -> dict:
        from sqlalchemy import select as _sel

        async with async_db_session() as db:
            stmt = _sel(AiWorkspaceCronModel).where(AiWorkspaceCronModel.is_deleted.is_(False))
            if category_id:
                stmt = stmt.where(AiWorkspaceCronModel.category_id == category_id)
            if target_type:
                stmt = stmt.where(AiWorkspaceCronModel.target_type == target_type)
            rows = (await db.execute(stmt.order_by(AiWorkspaceCronModel.id.desc()))).scalars().all()
            items = [cls._cron_dict(r) for r in rows]
            return {"total": len(items), "items": items}

    @classmethod
    async def list_cron_runs(cls, cron_id: int, limit: int = 50) -> list[dict]:
        """定时任务执行历史。

        数据源：`ai_call_logs` 中 `usage="cron"` 且 `app_id=cron_id` 的记录（每次调度
        /「立即执行」由 `run_scheduled_workspace_cron` 写入），含成败、耗时、错误与
        输出摘要——解决「只知道在干、不知道干成什么样」。
        """
        from app.plugin.module_ai.overview.model import AiCallLogModel

        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiCallLogModel)
                    .where(
                        AiCallLogModel.usage == "cron",
                        AiCallLogModel.app_id == cron_id,
                        AiCallLogModel.is_deleted.is_(False),
                    )
                    .order_by(AiCallLogModel.id.desc())
                    .limit(limit)
                )
            ).scalars().all()
            return [
                {
                    "id": r.id,
                    "created_time": r.created_time.strftime("%Y-%m-%d %H:%M:%S")
                    if r.created_time
                    else "",
                    "result": r.result or "success",
                    "latency_ms": int(r.latency_ms or 0),
                    "error": r.error or "",
                    "reply_preview": r.reply_preview or "",
                }
                for r in rows
            ]

    @staticmethod
    def _cron_dict(r: AiWorkspaceCronModel) -> dict:
        trigger = r.trigger or "cron"
        raw_args = r.trigger_args
        return {
            "id": r.id,
            "name": r.name,
            "description": r.description or "",
            "trigger": trigger,
            # interval 的 JSON 串还原为对象（前端组件直接用）；now 无参数 → null
            "trigger_args": TriggerUtil.load_args(trigger, raw_args),
            # 统一层人话描述（空/脏数据无法描述时为 None，前端回退显示原始参数）
            "trigger_describe": TriggerUtil.describe_args(trigger, raw_args),
            # 兼容字段：前端 C 阶段切到 trigger/trigger_args 之前仍读 `cron`
            "cron": (raw_args or "") if trigger == "cron" else "",
            "target_type": r.target_type or "agent",
            "target_id": r.target_id,
            "category_id": r.category_id,
            "enabled": bool(r.enabled),
            "last_run_time": TriggerUtil.to_local_str(r.last_run_time),
            "next_run_time": TriggerUtil.to_local_str(r.next_run_time),
            # 上次执行结果（卡片直接用；历史行没有就是空）
            "last_status": r.last_status or "",
            "last_duration_ms": r.last_duration_ms or 0,
            "last_message": r.last_message or "",
            "last_run_id": r.last_run_id or "",
            # 连续失败 / 自动停用（卡片上提示用）
            "fail_streak": int(r.fail_streak or 0),
            "auto_disabled": bool(r.auto_disabled),
            "fail_limit": _CRON_FAIL_STREAK_LIMIT,
        }

    @staticmethod
    def _resolve_trigger(
        trigger: str | None, trigger_args, legacy_cron: str | None, enabled: bool
    ) -> tuple[str, object | None]:
        """把请求里的触发配置解析为落库值 `(trigger, trigger_args)`。

        **字段优先**：`trigger` 显式提供（非空串）时以它为准；兼容字段 `cron` **仅在 `trigger`
        缺省时**才被解读 —— 非 cron 类型的前端仍会带上 `cron: ""`，若先看旧字段会把它误判成
        「空表达式 + 启用」而误报 400（C4 审查钉死的缺口）。

        - cron 表达式为空（未提供 / 显式空串）：**启用中** → 400（`_EMPTY_TRIGGER_MSG`，不留
          「已启用但永不触发」的静默失效）；**未启用** → `("cron", None)`（「未配置 / 清空配置」语义）；
        - 其余情况：统一层 `TriggerUtil.validate`（非法 → 400，原因原样回显）+ `normalize`
          （写入即规范化：`0 9 * * 1-5` → `0 9 * * mon,tue,wed,thu,fri`）。
        """
        name = trigger.strip() if isinstance(trigger, str) else ""
        args = trigger_args if name else legacy_cron
        if not name:
            name = "cron"
        if name == "cron" and (args is None or (isinstance(args, str) and not args.strip())):
            if enabled:
                raise CustomException(msg=_EMPTY_TRIGGER_MSG, code=400, status_code=400)
            return "cron", None
        ok, reason = TriggerUtil.validate(name, args)
        if not ok:
            raise CustomException(msg=reason, code=400, status_code=400)
        return TriggerUtil.normalize(name, args)

    # ---------- 与中心调度器的同步 ----------

    @staticmethod
    def _scheduler_running() -> bool:
        """中心调度器是否在运行（调度关闭的部署里没有任何作业）。"""
        from app.core.ap_scheduler import scheduler

        return bool(getattr(scheduler, "running", False))

    @staticmethod
    def _preview_next_run(trigger: str | None, trigger_args) -> datetime | None:
        """统一层的「下次运行时间」预览（`TriggerUtil.next_run`，cron 语义的唯一口径）。

        只在**作业不存在且调度器未运行**时用于回显（如 `SCHEDULER_ENABLED=False` 的部署：
        没有作业，但界面仍应看到「本来会在什么时候跑」）。正常路径一律以作业的值为准
        （作业是唯一真源）。遗留脏表达式（Quartz 写法等）返回 `None` 而不抛。
        """
        if not trigger_args:
            return None
        try:
            return TriggerUtil.next_run(trigger or "cron", trigger_args)
        except Exception as e:  # noqa: BLE001 脏表达式没有有效的下次运行时间
            log.debug(f"无法计算下次运行时间（{trigger} {trigger_args!r}）：{e!s}")
            return None

    @classmethod
    def _resolve_next_run(cls, job, trigger, trigger_args, enabled: bool) -> datetime | None:
        """该行应有的 `next_run_time`：作业优先（唯一真源），调度器未运行时回退统一层预览。

        - 作业在 → 用作业算出的时刻（改表达式 / 启停后随作业同步刷新）；
        - 作业不在 + 调度器**在运行** → `None`：禁用、未配置、或注册失败（脏表达式由列表的
          `needs_review` 标出），绝不显示一个凭空的时刻；
        - 作业不在 + 调度器**未运行**（调度关闭的部署）→ 统一层预览值。
        """
        job_next = getattr(job, "next_run_time", None) if job else None
        if job_next is not None:
            return job_next
        if enabled and not cls._scheduler_running():
            return cls._preview_next_run(trigger, trigger_args)
        return None

    @classmethod
    def _sync_cron_job(cls, cron_id: int, trigger: str | None, trigger_args, enabled: bool):
        """把定时任务行同步到中心调度器（幂等），返回注册后的作业（未注册时为 `None`）。

        - 启用 + 已配置表达式 → 注册/替换作业（同键替换，改表达式即换触发器）；
        - 启用 + `trigger="now"`（立即执行）→ 同样注册：`now` 按契约**无参数**
          （`trigger_args` 恒为 `None`），由统一层构造 `DateTrigger(now + 2s)` 的一次性作业
          （守卫口径与工作流侧逐字一致，A9 修「立即执行」静默失效）；
        - 禁用 / 未配置表达式 → 移除作业（幂等，不留幽灵触发）；
        - 遗留脏表达式（迁移被跳过、Quartz 写法）注册失败：**不留幽灵作业、也不把请求打成 500**
          ——该行在列表里由统一层标 `needs_review`，提示人工改写。

        **刻意不用 `sync_business_jobs`**：那是「按整表同步」的接口（会清理列表外的同前缀
        作业），单行增改用它会把本模块其它定时任务的作业一并删掉。
        `next_run_time` 从返回的作业读回（作业是唯一真源）。
        """
        from app.core.ap_scheduler import SchedulerUtil

        job_key = _job_key(cron_id)
        if not (enabled and (trigger_args or trigger == "now")):
            SchedulerUtil.remove_business_job(job_key)
            return None
        try:
            return SchedulerUtil.register_business_trigger(
                job_key,
                trigger or "cron",
                trigger_args,
                run_scheduled_workspace_cron,
                args=(cron_id,),
            )
        except Exception as e:  # noqa: BLE001 - 单行脏配置不得拖垮增改接口
            SchedulerUtil.remove_business_job(job_key)
            log.warning(f"工作台定时任务 #{cron_id} 的触发配置无法注册作业，已跳过：{e!s}")
            return None

    @classmethod
    async def write_back_cron_state(
        cls,
        cron_id: int,
        ran_at: datetime | None = None,
        status: str | None = None,
        duration_ms: int | None = None,
        message: str | None = None,
        run_id: str | None = None,
    ) -> None:
        """把作业的 `next_run_time` 回写定时任务行（状态单一真源）。

        取值口径见 `_resolve_next_run`：作业在就用作业的值；作业不在且调度器在运行则回写
        `None`（禁用 / 未配置 / 注册失败），避免库里残留一个凭空的「下次运行」时刻。
        `ran_at` 刻意做成可选：启动期同步只回写下次运行时间，**不得**把启动时刻误记成
        「上次运行」（否则界面会把「服务重启过」显示成「任务刚跑过」）。
        """
        from app.core.ap_scheduler import scheduler

        job = scheduler.get_job(_job_key(cron_id))
        disabled_now = False
        auto_name, auto_reason = "", ""
        try:
            async with async_db_session.begin() as db:
                row = await db.get(AiWorkspaceCronModel, cron_id)
                if not row or row.is_deleted:
                    return
                if ran_at is not None:
                    row.last_run_time = ran_at
                if status is not None:
                    auto_name = row.name or f"定时任务#{cron_id}"
                    auto_reason = message or ""
                    row.last_status = status
                    row.last_duration_ms = duration_ms or 0
                    row.last_message = (message or "")[:512]
                    row.last_run_id = run_id
                    # 连续失败计数：成功清零；失败累加，到上限自动停用（防止坏配置一直烧调用）
                    if status == "success":
                        row.fail_streak = 0
                        row.auto_disabled = False
                    else:
                        row.fail_streak = int(row.fail_streak or 0) + 1
                        if row.fail_streak >= _CRON_FAIL_STREAK_LIMIT and row.enabled:
                            row.enabled = False
                            row.auto_disabled = True
                            disabled_now = True
                row.next_run_time = cls._resolve_next_run(
                    job, row.trigger, row.trigger_args, bool(row.enabled)
                )
        except Exception as e:  # noqa: BLE001 状态回写失败不影响本轮执行
            log.warning(f"工作台定时任务 #{cron_id} 状态回写失败：{str(e)[:200]}")
        if disabled_now:
            # 自动停用后作业也要摘掉，不然它还会到点触发（虽然会被 enabled 守卫拦下）
            log.warning(
                f"[cron] 定时任务 #{cron_id} 连续失败 {_CRON_FAIL_STREAK_LIMIT} 次，已自动停用"
            )
            try:
                from app.core.ap_scheduler import SchedulerUtil

                SchedulerUtil.remove_business_job(_job_key(cron_id))
            except Exception as e:  # noqa: BLE001
                log.warning(f"[cron] 摘除自动停用的作业失败：{str(e)[:120]}")
            await _notify_cron_auto_disabled(
                cron_id, auto_name, _CRON_FAIL_STREAK_LIMIT, auto_reason
            )

    @classmethod
    async def _enabled_cron_rows(cls) -> list[AiWorkspaceCronModel]:
        """启用且未删除的定时任务行（启动期同步的唯一数据源）。"""
        async with async_db_session() as db:
            stmt = select(AiWorkspaceCronModel).where(
                AiWorkspaceCronModel.enabled.is_(True),
                AiWorkspaceCronModel.is_deleted.is_(False),
            )
            return (await db.execute(stmt)).scalars().all()

    @classmethod
    def _specs_of(cls, rows: list[AiWorkspaceCronModel]) -> list[tuple]:
        """把启用行转成中心调度器的作业规格（5 元组，末项为传给作业函数的位置参数）。

        **一律排除 `now`**（`trigger == "now"`）：`now` 是「保存时的一次性事件」，
        统一层在**注册时**才把它算成 `DateTrigger(now + 2s)` —— 若启动期也重建，
        每次服务重启都会把它重新算成「重启后 2 秒」＝**每次重启都重跑一次**。
        """
        return [
            (
                _job_key(r.id),
                r.trigger or "cron",
                r.trigger_args,
                run_scheduled_workspace_cron,
                (r.id,),
            )
            for r in rows
            if r.trigger_args and (r.trigger or "cron") != "now"
        ]

    @classmethod
    async def collect_job_specs(cls) -> list[tuple]:
        """收集「启用且有触发表达式且非 `now`」的定时任务规格，供启动期 `sync_business_jobs` 注册。

        每项为 5 元组 `(job_key, trigger, trigger_args, func, func_args)`。脏表达式不在
        这里过滤：`sync_business_jobs` 会逐条跳过并告警，不会因一行坏配置抹掉其余作业。
        """
        return cls._specs_of(await cls._enabled_cron_rows())

    @classmethod
    async def write_back_cron_states(cls) -> None:
        """启动期把启用行的 `next_run_time` 逐行从作业读回（作业是唯一真源）。

        重启后内存 jobstore 里的作业会按库重建，作业算出的下次触发时刻与库里上次落的值
        可能不同（时间已经走过），不刷新就会在列表里显示一个过去的时刻。
        """
        for row in await cls._enabled_cron_rows():
            await cls.write_back_cron_state(row.id)

    @classmethod
    async def create_cron(cls, data, auth) -> dict:
        trigger, trigger_args = cls._resolve_trigger(
            getattr(data, "trigger", None),
            getattr(data, "trigger_args", None),
            getattr(data, "cron", None),
            bool(data.enabled),
        )
        async with async_db_session() as db:
            row = AiWorkspaceCronModel(
                name=data.name,
                description=data.description,
                trigger=trigger,
                trigger_args=TriggerUtil.dump_args(trigger, trigger_args),
                target_type=data.target_type,
                target_id=data.target_id,
                category_id=data.category_id,
                enabled=data.enabled,
                created_id=auth.user.id,
                updated_id=auth.user.id,
            )
            db.add(row)
            await db.flush()
            cron_id = row.id
            # 先落库再注册作业：作业触发时按库里的行取状态，避免「作业已注册、库还没写」
            await db.commit()
            job = cls._sync_cron_job(cron_id, trigger, trigger_args, bool(data.enabled))
            # next_run_time 由作业回写（单一真源）：业务侧不再自算，两套口径必然漂移
            row.next_run_time = cls._resolve_next_run(
                job, trigger, trigger_args, bool(data.enabled)
            )
            await db.commit()
            await db.refresh(row)
        return cls._cron_dict(row)

    @classmethod
    async def update_cron(cls, cron_id: int, data, auth) -> dict | None:
        async with async_db_session() as db:
            row = await db.get(AiWorkspaceCronModel, cron_id)
            if not row or row.is_deleted:
                return None
            was_enabled = bool(row.enabled)
            for key in (
                "name",
                "description",
                "target_type",
                "target_id",
                "category_id",
                "enabled",
            ):
                val = getattr(data, key, None)
                if val is not None:
                    setattr(row, key, val)
            # 用户手动重新启用：把「连续失败 / 自动停用」清零，重新开始计
            if row.enabled and not was_enabled:
                row.fail_streak = 0
                row.auto_disabled = False
            trigger_in = getattr(data, "trigger", None)
            args_in = getattr(data, "trigger_args", None)
            legacy_in = getattr(data, "cron", None)
            if TriggerUtil.args_provided(trigger_in, legacy_in):
                # `row.enabled` 已按本次请求更新（上面循环），故按「生效后是否启用」判定
                trigger, trigger_args = cls._resolve_trigger(
                    trigger_in, args_in, legacy_in, bool(row.enabled)
                )
                row.trigger = trigger
                row.trigger_args = TriggerUtil.dump_args(trigger, trigger_args)
            elif row.enabled and not row.trigger_args and row.trigger != "now":
                # 只切「启用」而库里没有表达式：同样不留「已启用但永不触发」的行。
                # `now` 例外：它按契约**本就没有参数**（`trigger_args` 恒为 NULL），
                # 不是「未配置」——否则 `now` 行连「只改名字」的部分更新都会被误报 400
                # （A8 修正轮 I-1）。守卫的其余强度不变：显式提交「cron + 空参数 + 启用」
                # 仍由 `_resolve_trigger` 当场 400。
                raise CustomException(msg=_EMPTY_TRIGGER_MSG, code=400, status_code=400)
            row.updated_id = auth.user.id
            # 先落库再同步作业（同 create）：作业触发时按库里的行取状态
            trigger, trigger_args, enabled = row.trigger, row.trigger_args, bool(row.enabled)
            await db.commit()
            job = cls._sync_cron_job(cron_id, trigger, trigger_args, enabled)
            # next_run_time 由作业回写（单一真源）：禁用 / 未配置 / 注册失败一律回落 None
            row.next_run_time = cls._resolve_next_run(job, trigger, trigger_args, enabled)
            await db.commit()
            await db.refresh(row)
        return cls._cron_dict(row)

    @classmethod
    async def delete_cron(cls, cron_id: int, auth) -> None:
        async with async_db_session.begin() as db:
            row = await db.get(AiWorkspaceCronModel, cron_id)
            if not row or row.is_deleted:
                raise CustomException(msg="定时任务不存在")
            await db.delete(row)
        # 行已删除后再移除作业（幂等）：不留「行已没了、作业还在跑」的幽灵触发
        from app.core.ap_scheduler import SchedulerUtil

        SchedulerUtil.remove_business_job(_job_key(cron_id))

    @classmethod
    async def trigger_cron(cls, cron_id: int, background_tasks) -> str:
        """「立即执行一次」：校验行存在后，把执行挂到后台任务。

        返回 ``"ok"`` / ``"running"`` / ``"missing"``：
        - running：上一轮还没跑完（连点两下、或调度器刚触发），直接拒绝，
          避免同一个任务真的跑两遍（模型调用翻倍、`last_*` 互相覆盖）；
        - missing：行不存在或已删除。

        不直接 await 执行：目标运行可能远超 HTTP 超时时间；放 background_tasks
        让接口只负责入队，执行路径与调度器触发的是同一个 `run_scheduled_workspace_cron`。
        """
        async with async_db_session() as db:
            row = await db.get(AiWorkspaceCronModel, cron_id)
            if not row or row.is_deleted:
                return "missing"
        if cron_is_running(cron_id):
            return "running"
        background_tasks.add_task(run_scheduled_workspace_cron, cron_id)
        return "ok"

    @staticmethod
    async def _drain_text(stream) -> tuple[str, str | None, list[dict]]:
        """把整条流消费完，顺手攒出正文与工具调用（卡片「上次结果」/「执行过程」用）。

        帧是 Agno 原生 SSE，和 assistant 落会话时的口径一致：
        - ``RunContent`` → 正文（攒到 600 字就不再追加，但继续消费，不能中途 break）；
        - ``ToolCallStarted/Completed`` → 工具调用明细（名字、参数、结果、耗时）；
        - ``RunError`` → 失败（智能体被禁用时接口不抛异常、只发这一帧，
          不认它就会把失败记成成功）。

        返回 ``(正文摘要, 错误信息, 工具调用列表)``。
        """
        import json as _json
        import time as _t

        parts: list[str] = []
        size = 0
        err: str | None = None
        tools: list[dict] = []
        open_calls: dict[str, dict] = {}
        async for frame in stream:
            if "event: RunError" in frame:
                if not err:
                    try:
                        payload = _json.loads(frame.split("\ndata:", 1)[1].strip())
                        err = str(payload.get("error") or "执行失败")[:300]
                    except Exception:  # noqa: BLE001
                        err = "执行失败"
                continue
            if "event: ToolCall" not in frame:
                if "event: RunContent" not in frame:
                    continue
                if size > 600:
                    continue
                try:
                    payload = _json.loads(frame.split("\ndata:", 1)[1].strip())
                except Exception:  # noqa: BLE001 解析失败不影响执行
                    continue
                piece = payload.get("content")
                if isinstance(piece, str) and piece:
                    parts.append(piece)
                    size += len(piece)
                continue

            # 工具调用：Started 记起点，Completed 配对算耗时并落明细
            try:
                payload = _json.loads(frame.split("\ndata:", 1)[1].strip())
            except Exception:  # noqa: BLE001
                continue
            tool = payload.get("tool") or {}
            name = str(tool.get("tool_name") or "工具")
            call_id = str(tool.get("tool_call_id") or "") or name
            if "ToolCallStarted" in frame:
                open_calls[call_id] = {"name": name, "args": tool.get("tool_args"), "t0": _t.perf_counter()}
            elif "ToolCallCompleted" in frame:
                rec = open_calls.pop(call_id, None) or {"name": name, "args": None, "t0": _t.perf_counter()}
                ms = int((_t.perf_counter() - rec["t0"]) * 1000)
                result = tool.get("result")
                ok = not (isinstance(result, dict) and result.get("success") is False)
                tools.append(
                    {
                        "name": rec["name"] or name,
                        "args": rec["args"],
                        "result": result,
                        "ms": ms,
                        "ok": ok,
                    }
                )
        return " ".join("".join(parts).split())[:300], err, tools

    @classmethod
    async def _run_target(
        cls, target_type: str, target_id: int
    ) -> tuple[str, str | None, list[dict]]:
        """执行绑定的资产（三种目标都**真实运行**，不是只记一行日志）。

        - workflow：`run_schedule`（引擎直跑，无输入，落运行日志）；
        - agent / app：复用各自的流式执行入口并**消费完整个流**（没有非流式入口，
          这是唯一不改 agno 链路的做法）。`auth=None` + `session_id=None`：
          不落用户会话（`persist_session_exchange` 无 session_id 直接跳过），
          调用日志照记（`user_id=None`），与 workflow 的调度口径一致。

        返回 ``(正文摘要, 错误信息, 工具调用明细)``，只用于卡片与执行过程展示。
        """
        if target_type == "workflow":
            from app.plugin.module_ai.workflow.service import AiWorkflowService

            await AiWorkflowService.run_schedule(target_id)
            return "", None, []
        if target_type == "agent":
            from app.plugin.module_ai.agent.service import AiAgentService

            return await cls._drain_text(
                AiAgentService.run_ui_stream(target_id, list(_SCHEDULE_MESSAGES), None)
            )
        if target_type == "app":
            from app.plugin.module_ai.apps.service import run_app_ui_stream

            return await cls._drain_text(
                run_app_ui_stream(target_id, list(_SCHEDULE_MESSAGES), None)
            )
        log.warning(f"[workspace] 定时任务目标类型不支持：{target_type}#{target_id}")
        return "", None, []
