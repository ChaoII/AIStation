# 音频波形加载 CORS 解决方案（同源内容端点）设计

## 1. 背景与问题

音频事件标注（已合并）用 wavesurfer.js v7 通过 `fetch` 加载 presigned `play_url` 解码波形。该 `play_url` 由后端 boto3 生成，指向对象存储 **RustFS**（`RUSTFS_ENDPOINT`，默认 `http://127.0.0.1:9010`，桶 `aistation-annotation-{dev|prod}`）。

- 页面源：前端 `http://localhost:5180` → fetch `http://127.0.0.1:9010/...`，构成**跨源请求**，需对象存储桶配置 CORS（wavesurfer v7 用 `fetch` 加载 presigned `play_url` 解码波形）。
- 视频/图片走 `<video>`/`<img>` 标签加载（不受 CORS 约束）；**音频是首个依赖 `fetch` 的对象存储媒体**，故暴露此问题。
- 仓库**无任何桶级 CORS 配置**（无 `put_bucket_cors`），也无针对 RustFS 的反向代理。

**目标**：让音频波形能在浏览器正常加载解码，不依赖对象存储桶 CORS，采用**后端同源内容端点**方案。

## 2. 方案选择

| 方案 | 评估 |
|------|------|
| **后端同源内容端点** | 新增 `GET /api/v1/annotation/audio/content/{id}`，后端从 RustFS 读字节并经 `/api/v1`（前端已走 Vite/nginx 代理到后端，同源）返回；前端 wavesurfer 改用该同源 URL。**不依赖桶 CORS**，复用现有 `/api/v1` 代理链路，最小部署改动。● **选用**（**注意**：仅 `/api/v1` 前缀被 Vite（`vite.config.ts` proxy 键 `VITE_APP_BASE_API`）与 nginx（`location /api/v1`→backend:8001）代理；若只返回 `/annotation/...` 会 404，故 URL 必须含 `/api/v1` 前缀） |
| 桶 `put_bucket_cors` | 需 RustFS 暴露/支持 CORS 配置，且属部署/运维强依赖，不同环境易漏配 |
| 后端 `play_url` 改走同源转发 | 与上面本质相同，但保留两个入口语义重复 |

## 3. 后端设计

`backend/app/api/v1/module_annotation/dataset/audio_service.py` 新增：
- `stream_audio_content(audio_id)`：按 `audio_id` 取 `AnnotationAudioModel`（带数据集归属校验，参考 `get_play_url`/`get_content`），从 RustFS `get_object` 读取，返回**流式字节**（使用 boto3 `get_object` 的流式 `Body`，避免 ≤100MB 全量载入内存），并记录 `Content-Length`/`Content-Type`。

`audio_controller.py` 新增：
- `GET /audio/content/{audio_id}` → `StreamingResponse`（`media_type` 依扩展名，如 `audio/wav`/`audio/mpeg`/`audio/mp4`/`audio/ogg`/`audio/flac`，参考 `_EXT_CONTENT_TYPE`），`Content-Disposition: inline`。
- 鉴权 `AuthPermission(["annotation:dataset:query"])`（与 list/detail/play-url 一致）。

**保留** `GET /audio/play-url/{id}`（兼容既有调用与其它消费方），不删除。

## 4. 前端设计

- `frontend/src/api/module_annotation/audio.ts` 新增 `getAudioContentUrl(audio_id)` → 返回 `/api/v1/annotation/audio/content/${id}`（同源相对路径，`/api/v1` 前缀被 Vite/nginx 代理到后端；用 `import.meta.env.VITE_APP_BASE_API || "/api/v1"` 拼，与 `request.ts` baseURL 策略一致）。仅构造/返回该同源 URL，不预先拉字节。
- `AnnotationWorkbench.vue` 的 `initAudio`（audio 分支）：`audioUrl.value` 由 `getAudioPlayUrl(audio.id)` 改为 `getAudioContentUrl(audio.id)`（同源）。`AudioTimelineCanvas.vue` 的 wavesurfer `url: props.url` 改用该同源 URL，**并在 `fetchParams` 中带 `Authorization: Bearer <token>`**（content 端点有 `annotation:dataset:query` 鉴权，wavesurfer 原生 fetch 不带 token 会 401；token 取自 `Auth.getAccessToken()`）。
- 若需解码（wavesurfer 需完整字节），同源 `content` 端点返回完整音频字节（≤100MB，StreamingResponse），wavesurfer 正常解码，无跨源。
- 不影响图片/视频（仍走 `<img>/<video>` presigned）。

## 5. CORS 部署说明（保留作为文档）

若对象存储桶已能配置 CORS（RustFS/S3 支持），可选地在部署时对桶配置允许前端源，作为双保险；但**本方案不依赖**该配置，属可选项而非前提。

## 6. 测试

- 后端：`stream_audio_content` mock RustFS 返回字节、content 端点返回流式响应与正确 `media_type`/`Content-Length`、鉴权，音频归属校验，`Content-Disposition`。
- 前端：`getAudioContentUrl` 返回同源 URL；`Argument`/URL 断言单测。
- e2e：音频事件标注工作台波形加载（dev 栈：前端 fetch 同源 `/api/v1/annotation/audio/content/{id}` 经 Vite 代理转发并带 Bearer token，无 CORS），波形渲染回归。

## 7. 约束

- 不新增依赖；遵循 `AGENTS.md`（`el-*`、中文注释、成熟库）。
- 保留 `play_url` 兼容。
- 流式读取避免整文件内存峰值。
