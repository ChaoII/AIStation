import httpx
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from app.core.logger import logger
from app.config.setting import settings


class MediaServerClient:
    def __init__(self, base_url: str = "", secret: str = ""):
        base_url = base_url or settings.ZLM_BASE_URL
        secret = secret or settings.ZLM_SECRET
        self.base_url = base_url.rstrip("/")
        self.secret = secret
        self._client: Optional[httpx.AsyncClient] = None

    async def _request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        url = urljoin(f"{self.base_url}/", endpoint.lstrip("/"))
        data = {"secret": self.secret} if self.secret else {}
        if params:
            data.update(params)
        if not self._client:
            self._client = httpx.AsyncClient(timeout=10)
        try:
            resp = await self._client.post(url, data=data)
            resp.raise_for_status()
            result = resp.json()
            if result.get("code") != 0:
                raise Exception(result.get("msg", "ZLM API error"))
            return result.get("data") or result
        except Exception as e:
            logger.error(f"ZLM API call failed [{endpoint}]: {e}")
            raise

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def add_stream_proxy(self, url: str, stream_id: str, **kwargs) -> Dict:
        params = {
            "url": url,
            "stream_id": stream_id,
            "enable_rtsp": kwargs.get("enable_rtsp", True),
            "enable_rtmp": kwargs.get("enable_rtmp", True),
            "enable_hls": kwargs.get("enable_hls", True),
            "enable_fmp4": kwargs.get("enable_fmp4", False),
            "enable_audio": kwargs.get("enable_audio", True),
            "enable_mp4": kwargs.get("enable_mp4", False),
        }
        return await self._request("/index/api/addStreamProxy", params)

    async def close_stream(self, stream_id: str) -> Dict:
        return await self._request("/index/api/close_streams", {
            "stream_id": stream_id
        })

    async def get_media_list(self, scheme: str = "") -> List[Dict]:
        result = await self._request("/index/api/getMediaList", {"scheme": scheme})
        return result if isinstance(result, list) else []

    async def is_media_online(self, stream_id: str, app: str = "live") -> bool:
        result = await self._request("/index/api/getMediaList", {"app": app, "stream_id": stream_id})
        data = result if isinstance(result, list) else []
        return len(data) > 0

    async def start_record(self, stream_id: str, type: str = "mp4", app: str = "live") -> Dict:
        return await self._request("/index/api/startRecord", {
            "type": type, "app": app, "stream_id": stream_id,
        })

    async def stop_record(self, stream_id: str, type: str = "mp4", app: str = "live") -> Dict:
        return await self._request("/index/api/stopRecord", {
            "type": type, "app": app, "stream_id": stream_id,
        })

    async def get_record_status(self, stream_id: str, type: str = "mp4", app: str = "live") -> Dict:
        return await self._request("/index/api/getRecordStatus", {
            "type": type, "app": app, "stream_id": stream_id,
        })

    async def get_record_files(self, stream_id: str, app: str = "live", period: str = "") -> List[Dict]:
        result = await self._request("/index/api/getMp4RecordFile", {
            "app": app, "stream_id": stream_id, "period": period,
        })
        return result if isinstance(result, list) else []

    async def get_snap(self, stream_id: str, app: str = "live", timeout_sec: int = 10) -> bytes:
        url = f"{self.base_url}/index/api/getSnap"
        data = {"secret": self.secret, "app": app, "stream_id": stream_id, "timeout_sec": timeout_sec}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, data=data)
            resp.raise_for_status()
            return resp.content

    async def version(self) -> str:
        result = await self._request("/index/api/version")
        return result if isinstance(result, str) else ""

    def get_play_urls(self, stream_id: str, app: str = "live") -> Dict[str, str]:
        host = self.base_url.replace("http://", "").replace("https://", "")
        return {
            "webrtc": f"webrtc://{host}/rtc/{app}/{stream_id}",
            "flv": f"{self.base_url}/{app}/{stream_id}.flv",
            "hls": f"{self.base_url}/{app}/{stream_id}.hls.m3u8",
            "ws_flv": f"ws://{host}/{app}/{stream_id}.live.flv",
            "rtsp": f"rtsp://{host}/{app}/{stream_id}",
            "rtmp": f"rtmp://{host}/{app}/{stream_id}",
        }


media_server = MediaServerClient()
