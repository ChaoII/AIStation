"""SSE（Server-Sent Events）响应的共享契约。

为什么单点存放：SSE 有两个坑，**都不在端点代码里**，而是分别出在压缩中间件和
浏览器侧。漏掉任何一个，症状都是同一句「实时流不推送」，但排查方向完全相反，
所以必须集中成一处、并在测试里锁住。

坑一：必须声明 ``Content-Encoding: identity``
------------------------------------------------
:class:`app.core.middlewares.CustomGZipMiddleware` 继承了 starlette 的
``GZipMiddleware``，后者对**流式**响应会用 zlib 边收边压。zlib 在
``compresslevel=9`` 下把已写入的数据全部压在内部缓冲区里，**直到流关闭才吐**。

实测（``/train/task/{id}/metrics/stream``，229 帧共约 14KB）：

- ``Accept-Encoding: identity`` → 0.06 秒内补发 229 帧，格式完全正确
- ``Accept-Encoding: gzip``（浏览器的真实行为）→ **62 秒只发出 1 个 10 字节的
  gzip 头**，其余一帧不到

starlette 的 ``GZipResponder`` 对「响应自带 ``Content-Encoding``」有一条
**原样透传**的分支（源码里的 ``content_encoding_set`` 判断）。声明
``identity`` 即命中那条路，完全绕开压缩。``identity`` 在此语义准确——内容确实
未经任何内容编码。

坑二：反代缓冲
--------------
``Cache-Control: no-transform`` 与 ``X-Accel-Buffering: no`` 是穿透 nginx /
反向代理缓冲的标配，少一个实时性就没了（表现是「整块才到」）。
"""

from starlette.responses import StreamingResponse

#: SSE 响应头。**所有** ``text/event-stream`` 端点都必须用它，不要就地手写。
SSE_RESPONSE_HEADERS: dict[str, str] = {
    # no-transform：告诉下游代理不要压缩/转换响应体
    "Cache-Control": "no-cache, no-transform",
    # 关掉 nginx 的响应缓冲，否则 SSE 会被攒成一坨再发
    "X-Accel-Buffering": "no",
    # 关键：命中 starlette GZipResponder 的透传分支，绕开 zlib 对流式响应的缓冲
    "Content-Encoding": "identity",
}


def sse_response(gen, **kwargs) -> StreamingResponse:
    """构造一个带完整 SSE 响应头的 :class:`StreamingResponse`。

    用它而不是 ``StreamingResponse(media_type="text/event-stream")``：后者不会
    带上 :data:`SSE_RESPONSE_HEADERS`，于是 SSE 会被 GZip 中间件压成"不推送"。
    """
    return StreamingResponse(
        gen,
        media_type="text/event-stream",
        headers=dict(SSE_RESPONSE_HEADERS),
        **kwargs,
    )
