# SSE 在反向代理下的配置（AI 对话 / 办公室派活 / 工作流）

> 2026-10-26 核对：后端已按统一契约返回 SSE 响应头，**代码侧不需要再改**；这份文档只解决"上线后整块才到"的运维配置。

## 后端已经做了什么

所有 `text/event-stream` 端点统一走 `app/core/sse.py` 的 `sse_response()`（工作流的
`ui_stream_response()` 也继承了同一份头），线上实测响应头：

```
content-type: text/event-stream; charset=utf-8
cache-control: no-cache, no-transform
x-accel-buffering: no
content-encoding: identity      ← 关键：命中 starlette GZip 的透传分支
connection: keep-alive
```

两个坑（细节见 `app/core/sse.py` 顶部注释）：

1. **GZip 中间件会把 SSE 压成"不推送"**：zlib 在 level 9 下把数据压在内部缓冲，直到流关闭才吐。
   声明 `Content-Encoding: identity` 命中 starlette 的透传分支，完全绕开压缩。
   （`app/core/middlewares.py` 里对 `text/event-stream` 也做了显式跳过，双保险。）
2. **反代缓冲**：`Cache-Control: no-transform` + `X-Accel-Buffering: no` 是穿透 nginx 缓冲的标配。

## nginx 参考配置

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8001;
    proxy_http_version 1.1;

    # —— SSE 必需 ——
    proxy_buffering off;              # 不缓冲响应
    proxy_cache off;
    proxy_set_header Connection '';   # 关掉 keep-alive 到上游的复用（SSE 长连接）
    chunked_transfer_encoding on;

    # 长任务（团队派活/工作流可能跑几分钟）
    proxy_read_timeout 600s;
    proxy_send_timeout 600s;

    # 不要对 SSE 做 gzip（与后端 identity 头呼应，避免某些 nginx 版本仍然压）
    gzip off;
}
```

如果前面还有一层网关（Kong / APISIX / 云 LB），同样要关掉响应缓冲，并把读超时提到 ≥ 300s。

## 自检方法

```bash
curl -N -i -X POST http://<host>/api/v1/ai/agents/office/dispatch/stream \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"text":""}' | head -20
```

- 能看到 5 行头（尤其 `content-encoding: identity`、`x-accel-buffering: no`）= 后端没问题；
- 如果头对但**帧要等很久才一起出现**，问题在代理层，按上面的 nginx 配置改。

## 已知边界

- 后端不会主动发心跳注释（`: ping`）。如果中间代理的空闲超时 < 模型最长静默时间（例如团队协作时
  组长思考 90 秒以上），仍可能被代理断开。此时要么把代理空闲超时调到 ≥ 300s，要么后续加心跳。
- 前端断线后的行为见「AI 办公室」的断线处理（常驻提示条 + 重试 + 断线后补回结论）。
