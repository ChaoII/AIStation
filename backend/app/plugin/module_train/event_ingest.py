"""TorchKiln 简单模式事件接收：解析/物化逻辑（纯函数，便于测试）。

简单模式（子进程直调，无容器）下，训练侧把结构化事件通过
``POST /api/v1/train/internal/events`` 回调给本端；本模块负责：

- ``EventIngestBody``：请求体 schema（``task_id``/``seq``/``ts``/``type`` 之外
  的字段**平铺透传**，如 step 的 ``loss``/``epoch``、env 的 ``gpu``/``cpu``）；
- ``render_event_row``：把事件渲染为与 ``torchkiln_executor._row_from_event``
  **相同结构**的行（step 摊平 ``comps``、eval/best 摊平 ``metrics``，带
  ``_kind``/``seq``/``total_epochs`` 等）——保持前端行格式不变；
- ``update_usage_tasks``：环境指标台账更新钩子（Task 5 接线）。

⚠️ 渲染逻辑**不修改**容器路径的 ``_row_from_event``，而是独立复制其语义，
避免破坏已验证的容器模式链路。
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .torchkiln_client import EVENT_BEST, EVENT_END, EVENT_EVAL, EVENT_STEP

#: 事件基字段（渲染行时剔除，只留业务字段）
_EVENT_BASE_KEYS = ("task_id", "seq", "ts", "type")


class EventIngestBody(BaseModel):
    """事件接收请求体（字段平铺，extra 允许透传）。

    - ``task_id``：训练任务 ID（事件表外键）；
    - ``seq``：事件序号（任务内单调递增，幂等键的一部分）；
    - ``ts``：事件时间（epoch 秒，float；``insert_event`` 负责转 UTC aware）；
    - ``type``：事件类型（step/eval/best/end/env/failed/...）；
    - 其余字段按事件类型透传（如 step 的 loss/epoch，env 的 gpu/cpu/...）。
    """

    model_config = ConfigDict(extra="allow")

    task_id: int
    seq: int
    ts: float
    type: str


def render_event_row(ev: dict) -> dict | None:
    """把事件渲染为与 ``torchkiln_executor._row_from_event`` 同语义的独立实现
    （plan 要求不改现有函数，避免破坏容器路径）；如两者漂移，以本文件为准并同步。

    分支：
    - ``step``：``comps`` 摊平（仅 int/float 值），``total_epochs`` 取自事件
      ``epoch_num``（仅 int 时写入）；
    - ``eval``/``best``：``metrics`` 摊平（仅 int/float 值），``best`` 仅 best 事件
      为 True（eval 为 None），``fps`` 非 None 时写入；
    - ``end``：收尾帧（exit_reason/main_indicator/duration_sec）；
    - ``env``：环境指标（TorchKiln ``EnvSampler.sample()``），gpu/cpu/cpu_per_core/
      mem/disk/net 均为嵌套 dict/list，**不摊平**，原样透传（Task 7 前端按此取数）；
    - ``failed``：失败事件，字段由 TorchKiln 侧定（含 error/exit_reason 等），原样透传；
    - 未知 type：返回 None（不 publish，但事件仍落库——统一先 insert 再按行发布）。

    参数:
    - ev (dict): 完整事件（含 task_id/seq/ts/type 平铺字段）。

    返回:
    - dict | None: 渲染后的行（可直接 ``publish_metric`` 扇出）；未知类型返回 None。
    """
    etype = ev.get("type")
    seq = ev.get("seq")
    # 与容器路径同义：TorchKiln 事件带 ``epoch_num``（总轮次），必须改写成
    # 本项目约定的 ``total_epochs``——前端「Epoch N/M」卡片与进度条按它取分母。
    total_epochs = ev.get("epoch_num")
    if etype == EVENT_STEP:
        row = {
            "_kind": EVENT_STEP,
            "seq": seq,
            "epoch": ev.get("epoch"),
            "global_step": ev.get("global_step"),
            "loss": ev.get("loss"),
            "lr": ev.get("lr"),
            "ips": ev.get("ips"),
            "mem_reserved": ev.get("mem_reserved"),
        }
        if isinstance(total_epochs, int):
            row["total_epochs"] = total_epochs
        for k, v in (ev.get("comps") or {}).items():
            if isinstance(v, (int, float)):
                row[k] = v
        return row
    if etype in (EVENT_EVAL, EVENT_BEST):
        row = {"_kind": etype, "seq": seq, "best": etype == EVENT_BEST or None}
        row["epoch"] = ev.get("epoch")
        row["global_step"] = ev.get("global_step")
        row["main_indicator"] = ev.get("main_indicator")
        row["main_indicator_mode"] = ev.get("main_indicator_mode")
        row["main_value"] = ev.get("main_value")
        if isinstance(total_epochs, int):
            row["total_epochs"] = total_epochs
        if ev.get("fps") is not None:
            row["fps"] = ev["fps"]
        # metrics 子对象摊平，前端按 {epoch, 指标名: 值} 取值
        for k, v in (ev.get("metrics") or {}).items():
            if isinstance(v, (int, float)):
                row[k] = v
        return row
    if etype == EVENT_END:
        row = {
            "_kind": EVENT_END,
            "seq": seq,
            "exit_reason": ev.get("exit_reason"),
            "epoch": ev.get("epoch"),
            "main_indicator": ev.get("main_indicator"),
            "main_value": ev.get("main_value"),
            "duration_sec": ev.get("duration_sec"),
        }
        if isinstance(total_epochs, int):
            row["total_epochs"] = total_epochs
        return row
    if etype in ("env", "failed"):
        # env/failed：业务字段原样平铺进事件（嵌套结构不摊平），只剔除事件基字段
        fields = {k: v for k, v in ev.items() if k not in _EVENT_BASE_KEYS}
        return {"_kind": etype, "seq": seq, **fields}
    return None


async def update_usage_tasks(ev: dict) -> None:
    """环境指标台账更新钩子。

    Task 5 接线：``type == "env"`` 时更新 Redis 资源台账
    （GPU/CPU/内存/磁盘/网络占用），供后续资源占用展示与调度参考。
    第一版为 no-op 占位。

    参数:
    - ev (dict): 完整事件（含 task_id/seq/ts/type 平铺字段）。

    返回:
    - None: 无返回。
    """
    return None
