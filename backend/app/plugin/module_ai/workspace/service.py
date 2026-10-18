"""AI 工作台服务：分类树 CRUD + 多类型条目聚合。"""
from __future__ import annotations

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


async def run_scheduled_workspace_cron(cron_id: int) -> None:
    """中心调度器作业入口：执行工作台定时任务绑定的资产，并回写运行状态。

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
    try:
        await WorkspaceService._run_target(target_type, target_id)
    except Exception as exc:  # noqa: BLE001 单次执行失败不抛出，避免污染作业状态
        log.error(f"工作台定时任务 #{cron_id} 执行失败：{exc}")
    finally:
        # 只有真正执行过的这一轮才回写 `last_run_time`（被跳过的行不记「刚跑过」）
        await WorkspaceService.write_back_cron_state(cron_id, ran_at=started)


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
                "next_run_time": cls._g(row, "next_run_time"),
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
            "last_run_time": r.last_run_time,
            "next_run_time": r.next_run_time,
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
    async def write_back_cron_state(cls, cron_id: int, ran_at: datetime | None = None) -> None:
        """把作业的 `next_run_time` 回写定时任务行（状态单一真源）。

        取值口径见 `_resolve_next_run`：作业在就用作业的值；作业不在且调度器在运行则回写
        `None`（禁用 / 未配置 / 注册失败），避免库里残留一个凭空的「下次运行」时刻。
        `ran_at` 刻意做成可选：启动期同步只回写下次运行时间，**不得**把启动时刻误记成
        「上次运行」（否则界面会把「服务重启过」显示成「任务刚跑过」）。
        """
        from app.core.ap_scheduler import scheduler

        job = scheduler.get_job(_job_key(cron_id))
        try:
            async with async_db_session.begin() as db:
                row = await db.get(AiWorkspaceCronModel, cron_id)
                if not row or row.is_deleted:
                    return
                if ran_at is not None:
                    row.last_run_time = ran_at
                row.next_run_time = cls._resolve_next_run(
                    job, row.trigger, row.trigger_args, bool(row.enabled)
                )
        except Exception as e:  # noqa: BLE001 状态回写失败不影响本次运行结果
            log.warning(f"工作台定时任务 #{cron_id} 状态回写失败：{str(e)[:200]}")

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
    async def _run_target(cls, target_type: str, target_id: int) -> None:
        """执行绑定的资产（工作流用其 run_schedule；agent/app 由对应 run 非流式执行）。"""
        if target_type == "workflow":
            from app.plugin.module_ai.workflow.service import AiWorkflowService

            await AiWorkflowService.run_schedule(target_id)
            return
        # agent / app：暂不做非流式执行，仅记录（后续接入）
        print(f"ℹ️ 定时任务目标 {target_type}#{target_id} 执行（非流式执行待接入）", flush=True)
