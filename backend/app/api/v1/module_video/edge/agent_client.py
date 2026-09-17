"""边缘 Agent 控制面客户端：经 httpx 下发/启停 TaskConfig。"""
from typing import Any

import httpx

from app.config.setting import settings
from app.core.exceptions import CustomException
from app.utils.url_guard import UnsafeUrlError, validate_outbound_url


class EdgeAgentClient:
    """封装与边缘 Agent 控制面（spec §6/§7）的 REST 交互。

    控制面契约（见 ModelDeploy 交接文档）：
    - `POST {control_url}/api/v1/tasks`（下发 TaskConfig）
    - `POST {control_url}/api/v1/tasks/{task_id}/start|stop`
    - `DELETE {control_url}/api/v1/tasks/{task_id}`
    鉴权：`Authorization: Bearer {secret}`（secret 非空时携带）。
    """

    def __init__(self, control_url: str, secret: str | None = None, timeout: float = 10.0) -> None:
        self.control_url = (control_url or "").rstrip("/")
        # SSRF 防护（审计 #12）：所有出站 Agent 请求共用此入口，构造即拦截危险地址
        if self.control_url:
            try:
                validate_outbound_url(
                    self.control_url,
                    block_private=settings.EDGE_CONTROL_URL_BLOCK_PRIVATE,
                    allowed_hosts=set(settings.EDGE_CONTROL_URL_ALLOWED_HOSTS) or None,
                )
            except UnsafeUrlError as e:
                raise CustomException(
                    msg=f"边缘控制面地址不安全：{e}", code=400, status_code=400
                ) from e
        self.secret = (secret or "").strip()
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.secret:
            headers["Authorization"] = f"Bearer {self.secret}"
        return headers

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        url = f"{self.control_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(method, url, headers=self._headers(), **kwargs)
        except httpx.HTTPError as e:
            raise CustomException(msg=f"边缘 Agent 请求失败: {method} {url} ({e})", code=502, status_code=502) from e

        if response.status_code >= 400:
            raise CustomException(
                msg=f"边缘 Agent 返回错误 {response.status_code}: {response.text[:200]}",
                code=502,
                status_code=502,
            )
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as e:
            raise CustomException(msg=f"边缘 Agent 响应非 JSON: {response.text[:200]}", code=502, status_code=502) from e

    async def dispatch(self, config: dict) -> dict:
        """下发 TaskConfig（创建/更新任务）。"""
        return await self._request("POST", "/api/v1/tasks", json=config)

    async def start(self, task_id: int) -> dict:
        """启动边缘任务。"""
        return await self._request("POST", f"/api/v1/tasks/{task_id}/start")

    async def stop(self, task_id: int) -> dict:
        """停止边缘任务。"""
        return await self._request("POST", f"/api/v1/tasks/{task_id}/stop")

    async def delete(self, task_id: int) -> dict:
        """删除边缘任务。"""
        return await self._request("DELETE", f"/api/v1/tasks/{task_id}")

    async def fetch_snapshot(self, task_id: int, timeout: float = 5.0) -> bytes:
        """取 Agent 侧最新帧 JPEG（二进制，绕开仅处理 JSON 的 _request）。"""
        url = f"{self.control_url}/api/v1/tasks/{task_id}/snapshot.jpg"
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, headers=self._headers())
        except httpx.HTTPError as e:
            raise CustomException(msg=f"边缘快照请求失败: {url} ({e})", code=502, status_code=502) from e
        if response.status_code >= 400:
            raise CustomException(
                msg=f"边缘快照返回错误 {response.status_code}",
                code=502,
                status_code=502,
            )
        if not response.content:
            raise CustomException(msg="边缘快照为空", code=502, status_code=502)
        return response.content
