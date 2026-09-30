"""TorchKiln 训练服务（自研平台 D:\\TorchKiln）的 HTTP 客户端。

设计要点
--------
1. **薄客户端**：AIStation 只负责"提需求 + 展示"，真正的执行、GPU 排队、
   容器生命周期、指标产出都在 TorchKiln 服务里。这样 AIStation 不再需要
   自己管容器、不再解析日志。
2. **超参零映射**：`hyperparams.params` 里的点分键（如 ``Global.epoch_num``）
   原样作为 ``-o Key.Sub=value`` 透传，**不需要**在两端各维护一张映射表——
   这是接自研平台相对接第三方框架最大的收益。
3. **指标走契约**：``metrics.jsonl`` 由训练侧产出，服务只 tail 转发。
   本客户端消费 SSE，把事件原样落 ``TrainTask.metrics_log``，前端据此画曲线。
4. **幂等**：提交带 ``Idempotency-Key=aistation-train-{task_id}``。
   客户端超时重试/服务重启后重提都不会重复排队烧卡。

配置（app/config/setting.py）
    TORKILN_SERVICE_URL / TORKILN_SERVICE_TOKEN / TORKILN_TIMEOUT
"""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config.setting import settings

log = logging.getLogger(__name__)

#: SSE 事件类型 -> 内部 kind
EVENT_STEP = "step"
EVENT_EVAL = "eval"
EVENT_BEST = "best"
EVENT_END = "end"
#: 服务端在作业终结时另发的一帧（不是 metrics.jsonl 里的事件）
EVENT_JOB_END = "__end__"


class TorchKilnError(RuntimeError):
    """训练服务调用失败（连接不上/返回 4xx/5xx/契约不符）。

    消息会直接写进 ``TrainTask.error_log``，因此必须**面向用户可读**：
    写清楚是"服务没起来"还是"模型名不存在"，而不是抛原始堆栈。
    """


class TorchKilnUnavailable(TorchKilnError):
    """服务不可达（连接拒绝/超时）——通常是服务没启动或地址配错。"""


def _base_url() -> str:
    return (settings.TORKILN_SERVICE_URL or "").rstrip("/")


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    h = {"Accept": "application/json"}
    token = (settings.TORKILN_SERVICE_TOKEN or "").strip()
    if token:
        h["Authorization"] = f"Bearer {token}"
    if extra:
        h.update(extra)
    return h


def _wrap_error(exc: Exception, what: str) -> TorchKilnError:
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
        return TorchKilnUnavailable(
            f"无法连接 TorchKiln 训练服务({_base_url()}): {exc}。"
            f"请确认服务已启动，或检查 setting.TORKILN_SERVICE_URL（{what}）"
        )
    if isinstance(exc, httpx.HTTPStatusError):
        detail = ""
        try:
            detail = json.dumps(exc.response.json(), ensure_ascii=False)[:400]
        except Exception:
            detail = exc.response.text[:400]
        return TorchKilnError(f"TorchKiln 服务返回 {exc.response.status_code}（{what}）: {detail}")
    if isinstance(exc, httpx.TimeoutException):
        return TorchKilnUnavailable(f"TorchKiln 服务响应超时（{what}）: {exc}")
    if isinstance(exc, TorchKilnError):
        return exc
    return TorchKilnError(f"TorchKiln 服务调用失败（{what}）: {type(exc).__name__}: {exc}")


class TorchKilnClient:
    """TorchKiln 服务客户端。

    用法::

        async with TorchKilnClient() as c:
            job = await c.submit_job(spec, idempotency_key="aistation-train-7")
            async for ev in c.stream_metrics(job["job_id"]):
                ...
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float | None = None,
    ):
        self.base_url = (base_url or _base_url()).rstrip("/")
        self.token = token if token is not None else (settings.TORKILN_SERVICE_TOKEN or "")
        self.timeout = timeout if timeout is not None else float(settings.TORKILN_TIMEOUT)
        if not self.base_url:
            raise TorchKilnError("未配置 TORKILN_SERVICE_URL")
        self._client: httpx.AsyncClient | None = None
        # SSE 用独立连接：一条指标流可能挂几小时，不能和普通 API 抢连接池
        self._stream_client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------ 生命周期
    async def __aenter__(self) -> TorchKilnClient:
        self._client = httpx.AsyncClient(
            base_url=self.base_url, timeout=self.timeout,
            headers=_headers(), follow_redirects=True)
        self._stream_client = httpx.AsyncClient(
            base_url=self.base_url, timeout=None, headers=_headers(),
            follow_redirects=True)
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        for c in (self._client, self._stream_client):
            if c is not None:
                try:
                    await c.aclose()
                except Exception as e:  # noqa: BLE001
                    log.debug("torchkiln client close: {}", e)
        self._client = self._stream_client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise TorchKilnError("TorchKilnClient 未初始化，请用 async with")
        return self._client

    # ------------------------------------------------------------ 普通 API
    async def _get(self, path: str, params: dict | None = None, what: str = ""):
        try:
            r = await self.client.get(path, params=params)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            raise _wrap_error(e, what or path) from e

    async def _post(self, path: str, body: Any, headers: dict | None = None,
                    what: str = ""):
        try:
            r = await self.client.post(
                path, json=body, headers=_headers(headers),
                timeout=float(settings.TORKILN_SUBMIT_TIMEOUT))
            r.raise_for_status()
            return r.json()
        except Exception as e:
            raise _wrap_error(e, what or path) from e

    async def info(self) -> dict:
        """服务与框架的版本/能力声明（用于兼容性判断）。"""
        return await self._get("/api/v1/info", what="info")

    async def healthz(self) -> dict:
        return await self._get("/healthz", what="healthz")

    async def list_models(self, task: str | None = None, family: str | None = None,
                          name: str | None = None) -> list[dict]:
        """模型清单（TorchKiln configs/ 全量扫描，加模型无需改本项目）。"""
        params = {k: v for k, v in
                  (("task", task), ("model_family", family), ("name", name)) if v}
        data = await self._get("/api/v1/models", params=params or None, what="models")
        return data.get("items") or []

    async def model_schema(self, model_name: str, overrides: list[str] | None = None) -> dict:
        """超参 schema：类型/默认值/范围/控件/分组/中文字段名（前端动态表单用）。"""
        params = {"o": " ".join(overrides)} if overrides else None
        return await self._get(
            f"/api/v1/models/{model_name}/schema", params=params, what="schema")

    async def submit_job(self, spec: dict, idempotency_key: str,
                         user_id: str | None = None, tenant: str | None = None) -> dict:
        headers = {"Idempotency-Key": idempotency_key}
        if user_id:
            headers["X-User-Id"] = str(user_id)
        if tenant:
            headers["X-Tenant"] = str(tenant)
        return await self._post(
            "/api/v1/train/jobs", spec, headers=headers, what="submit_job")

    async def get_job(self, job_id: str) -> dict:
        return await self._get(f"/api/v1/train/jobs/{job_id}", what="get_job")

    async def list_jobs(self, status: str | None = None, user_id: str | None = None,
                        limit: int = 50, offset: int = 0) -> dict:
        params = {k: v for k, v in
                  (("status", status), ("user_id", user_id)) if v}
        params.update({"limit": limit, "offset": offset})
        return await self._get("/api/v1/train/jobs", params=params, what="list_jobs")

    async def cancel_job(self, job_id: str) -> dict:
        return await self._post(
            f"/api/v1/train/jobs/{job_id}/cancel", {}, what="cancel_job")

    async def metrics(self, job_id: str, offset: int = -1, limit: int = 5000) -> list[dict]:
        """按 seq 补发历史指标（前端刷新/断线重连用）。"""
        data = await self._get(
            f"/api/v1/train/jobs/{job_id}/metrics",
            params={"offset": offset, "limit": limit}, what="metrics")
        return data.get("items") or []

    async def logs(self, job_id: str, tail: int = 500) -> list[str]:
        data = await self._get(
            f"/api/v1/train/jobs/{job_id}/logs", params={"tail": tail}, what="logs")
        return data.get("lines") or []

    async def fetch_file(self, job_id: str, filename: str, dest: str) -> str:
        """把作业产物（如 best_accuracy.pth）拉回本机。

        训练服务可能与本项目不在同一台机器/容器里，因此权重必须能下载回来。
        """
        url = f"{self.base_url}/api/v1/train/jobs/{job_id}/artifacts/{filename}"
        try:
            async with self._stream_client.stream("GET", url) as r:
                r.raise_for_status()
                with open(dest, "wb") as f:
                    async for chunk in r.aiter_bytes(1024 * 256):
                        f.write(chunk)
        except Exception as e:
            raise _wrap_error(e, f"下载产物 {filename}") from e
        return dest

    # ------------------------------------------------------------ SSE 流
    async def _sse(self, path: str, params: dict | None,
                   headers: dict | None = None) -> AsyncIterator[tuple[str, str, str]]:
        """SSE 读取器，产出 ``(event, id, data)``。

        断点续传：``Last-Event-ID`` 由调用方从上一次收到的 id 传入，服务端会
        **先补发缺口再切实时**，已消费过的不会重发。
        """
        if self._stream_client is None:
            raise TorchKilnError("TorchKilnClient 未初始化，请用 async with")
        url = self.base_url + path
        try:
            async with self._stream_client.stream(
                "GET", url, params=params, headers=_headers(headers)
            ) as r:
                if r.status_code >= 400:
                    body = (await r.aread()).decode("utf-8", "replace")[:300]
                    raise TorchKilnError(
                        f"SSE {path} 返回 {r.status_code}: {body}")
                event, eid = "message", None
                async for raw in r.aiter_lines():
                    if raw is None:
                        continue
                    line = raw.rstrip("\r")
                    if not line:
                        event, eid = "message", None
                        continue
                    if line.startswith(":"):        # 心跳/注释
                        continue
                    if line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("id:"):
                        eid = line[3:].strip()
                    elif line.startswith("data:"):
                        yield event, eid, line[5:].lstrip()
        except (httpx.RemoteProtocolError, httpx.ReadError) as e:
            # 服务端在作业终态后主动收流，属正常语义；让调用方按"流结束"处理
            log.debug("torchkiln SSE {} 结束: {}", path, e)
            return
        except TorchKilnError:
            raise
        except Exception as e:
            raise _wrap_error(e, f"SSE {path}") from e

    async def stream_metrics(self, job_id: str, offset: int = -1,
                             last_event_id: str | None = None) -> AsyncIterator[dict]:
        """指标事件流。产出 dict（含 ``type``/``seq``）；作业终结时最后收一条
        ``{"__end__": True, ...}``。"""
        headers = {"Last-Event-ID": last_event_id} if last_event_id else None
        params = {"offset": offset}
        async for event, _eid, data in self._sse(
                f"/api/v1/train/jobs/{job_id}/metrics/stream", params, headers):
            try:
                obj = json.loads(data)
            except (ValueError, TypeError):
                log.debug("忽略无法解析的 SSE data: %.120s", data)
                continue
            if isinstance(obj, dict) and obj.get("__end__"):
                yield obj
                return
            if isinstance(obj, dict):
                obj.setdefault("type", event)
                yield obj

    async def stream_logs(self, job_id: str, tail: int = 200) -> AsyncIterator[str]:
        params = {"tail": tail}
        async for event, _eid, data in self._sse(
                f"/api/v1/train/jobs/{job_id}/logs/stream", params):
            if event == "end":
                return
            yield data


async def probe_service() -> dict:
    """健康探测：给"训练"页面判断服务是否可用，避免用户点了开始才报错。"""
    if not settings.TORKILN_ENABLED:
        return {"available": False, "reason": "已通过 setting.TORKILN_ENABLED 关闭 TorchKiln 接入"}
    try:
        async with TorchKilnClient() as c:
            info = await c.info()
        return {"available": True, "url": _base_url(), **(info or {})}
    except TorchKilnError as e:
        return {"available": False, "url": _base_url(), "reason": str(e)}


def build_job_spec(
    model_name: str,
    params: dict[str, Any] | None = None,
    dataset: dict[str, str] | None = None,
    resources: dict[str, Any] | None = None,
    seed: int | None = None,
    labels: dict[str, str] | None = None,
) -> dict:
    """把 ``TrainTask.hyperparams`` 组装成服务端的 ``JobSpec``（声明式）。

    ⚠️ 只放**用户可调**的超参到 ``params``；``Global.save_model_dir`` 与
    ``Global.metrics_sink`` 由服务端强制注入，这里传了也会被覆盖。
    """
    spec: dict[str, Any] = {
        "spec_version": "1.0",
        "framework": "torchkiln",
        "model_name": model_name,
        "params": dict(params or {}),
    }
    if dataset:
        spec["dataset"] = {k: v for k, v in dataset.items() if v}
    if resources:
        spec["resources"] = resources
    if seed is not None:
        spec["seed"] = int(seed)
    if labels:
        spec["labels"] = labels
    return spec
