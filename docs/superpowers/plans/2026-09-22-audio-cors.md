# 音频波形加载 CORS 同源内容端点实施计划

> brief: `docs/superpowers/specs/2026-09-22-audio-cors-design.md`
> 目标：新增后端同源音频内容端点，前端 wavesurfer 改用同源 URL，消除对对象存储桶 CORS 的依赖。保留 `play_url` 兼容。

## 关键约定
- 分支 `feat/audio-cors-endpoint`（base = spec `638ab0e`）。
- 后端 `prefix="/annotation"`；新端点 `GET /annotation/audio/content/{id}`，鉴权 `annotation:dataset:query`。
- 流式读取 RustFS（boto3 `get_object` Body），避免整文件内存峰值；`Content-Length`/`Content-Type` 依扩展名。
- 前端 `getAudioContentUrl` 返回同源相对路径；workbench `initAudio` 换用。
- 遵循 AGENTS.md：`el-*`、中文注释、局部改动；不新增依赖。
- 子代理 prompt 用纯中文精简措辞避免敏感词拦截。
- 后端 `uv run pytest tests/...`；前端 `pnpm run test:unit`/`type-check`；e2e `npx playwright test`（dev 栈在跑）。

## 任务分解

### Task 1 — 后端 audio content 流式端点
- `dataset/audio_service.py` 新增 `stream_audio_content(audio_id)`：按 `audio_id` 取 `AnnotationAudioModel`（含数据集归属校验，参考 `get_play_url`/`get_content`），从 RustFS `get_object` 返回流式字节。
- `dataset/audio_controller.py` 新增 `GET /audio/content/{audio_id}` → `StreamingResponse`（media_type 依扩展名 `_EXT_CONTENT_TYPE`，Content-Disposition inline，Content-Length），鉴权 `annotation:dataset:query`。
- 保留 `play-url` 端点。
- 单测：stream_audio_content mock RustFS 字节、content 端点流式响应 + media_type + Content-Length、鉴权、归属校验。

### Task 2 — 前端改用同源 content URL
- `api/module_annotation/audio.ts` 新增 `getAudioContentUrl(audio_id)` 返回同源相对路径 `/annotation/audio/content/${id}`（含单测）。
- `AnnotationWorkbench.vue` 视频/音频分支：`initAudio` 中 `audioUrl` 改用 `getAudioContentUrl(audio.id)`；`AudioTimelineCanvas.vue` wavesurfer `url: props.url` 用同源 URL。
- 单测 + type-check 无新增 annotation 错误。

### Task 3 — e2e 与回归
- `frontend/e2e/create-audio-event.spec.ts` 确认波形加载走同源 content（origin 同源，无 CORS）；补/改断言；跑回归（音频/文本/视频/时间序列/smoke/workbench）。
- 无代码改动则只做验证。

## 账本
`.superpowers/sdd/audio-cors-progress.md`（gitignored）。

## 完工标准
后端单测 + 前端单测 + type-check + e2e（含音频波形回归）全通过；视觉核对波形正常；`play_url` 兼容保留。
