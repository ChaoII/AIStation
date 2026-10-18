"""SSE 响应契约守卫：所有 ``text/event-stream`` 响应都必须带共享 SSE 头。

为什么值得一条专门守卫：缺 ``Content-Encoding: identity`` 时，starlette 的
``GZipMiddleware`` 会用 zlib **边收边压**；浏览器默认发 ``Accept-Encoding: gzip``，
实测（见 ``app/core/sse.py`` 的实测记录）「62 秒只发出 1 个 10 字节的 gzip 头，
其余一帧不到」——症状是「实时流不推送」，但根因与业务代码无关，极难定位。
故在此锁死：契约本身 + 所有 SSE 响应都必须走共享头。
"""
import pathlib

from app.core.sse import SSE_RESPONSE_HEADERS


def test_shared_headers_contain_identity():
    """契约本身：identity 是绕开 GZip 流式压缩的开关，不能丢。"""
    assert SSE_RESPONSE_HEADERS.get("Content-Encoding") == "identity"
    assert SSE_RESPONSE_HEADERS.get("X-Accel-Buffering") == "no"
    assert "no-transform" in (SSE_RESPONSE_HEADERS.get("Cache-Control") or "")


def test_all_sse_responses_use_shared_headers():
    """任何构造 ``text/event-stream`` 响应的文件都必须引用共享头或 sse_response。"""
    base = pathlib.Path(__file__).resolve().parents[1] / "app"
    offenders: list[str] = []
    for f in base.rglob("*.py"):
        src = f.read_text(encoding="utf-8", errors="replace")
        uses_sse_media = any(
            "media_type" in ln and "text/event-stream" in ln for ln in src.splitlines()
        )
        if not uses_sse_media:
            continue
        if "sse_response" in src or "SSE_RESPONSE_HEADERS" in src:
            continue
        offenders.append(str(f.relative_to(base)))
    assert not offenders, (
        "以下文件手写了 SSE 响应头，必须改用 app/core/sse.py 的 sse_response / "
        "SSE_RESPONSE_HEADERS（否则浏览器下会被 GZip 缓冲、表现为「不推送」）：\n"
        + "\n".join(offenders)
    )
