# Phase 3：模型预测 + 部署 + 视频推理 设计

> 创建日期：2026-09-12
> 状态：已确认（用户认可范围与关键决策）
> 所属程序：`2026-09-11-pipeline-optimization-program-design.md`

## 背景

预测（`predict_executor.py`）、部署（`deploy_executor.py`）与视频推理（`app/api/v1/module_video/inference/`）是链路末端。审查发现：PaddleX 预测参数全丢、结果用 presigned URL 会过期、部署重启后停不掉真实容器、OCR 部署整图识别且配置硬编码、视频推理依赖未装/重复拉起/布控时段与 ROI 形同虚设、报警快照无 HTTP 路由。这些问题让"看起来能跑"的功能在真实环境不可用。

## 范围

1. **批量预测**：PaddleX `-o` 参数、device 处理、结果对象键存储 + 按需重签 + 清理、状态守卫。
2. **部署**：注册表重建/周期对账、停/删真实容器、端口复用、规格驱动配置、rec 裁剪识别、续期重启、超参透传、健康与日志。
3. **视频推理**：worker PID 防重、布控时段/灵敏度/ROI 生效、报警快照 HTTP 路由、类别名、规则匹配。
4. **前端**：预测结果查看器、部署日志/详情/det-rec 判别、视频布控 UI 接线。

## 关键决策（已确认）

| 决策点 | 结论 |
|---|---|
| 预测结果存储 | DB 存对象键；列表/详情按需重签 URL；删除预测清理对象存储 |
| 部署生命周期 | 启动按 DB `container_id` 重建注册表 + 周期对账；stop/delete 必停真实容器；端口可复用 stopped/failed |
| 部署服务 | 保留 FastAPI 生成器；rec 裁剪框识别；配置由模型规格驱动；续期 Key 触发容器重建；超参透传；避免每次 `pip install` |
| 视频推理依赖 | 维持 0A 的可用性探测 + 明确降级；worker PID 记录防重复 |
| 布控时段/ROI/灵敏度 | 后端真实解析并下发 worker |
| 报警快照 | 受控 HTTP 路由提供；DB 存相对文件名 |
| 前端 | 部署日志/详情查看器、det/rec 判别、预测结果查看器 |

## 组件设计

### A. 批量预测
- `_build_paddlex_predict_cmd`：单个 `-o` + 空格分隔全部 opt；`use_gpu` 由 device 决定。
- Ultralytics 命令带 `device=`；`device="cpu"` 不传 GPU 请求。
- 结果：`result_images` 存对象键列表，`result_zip_path` 存对象键；新增 `sign_predict_results(predict) -> dict` 在接口层转 URL；删除预测时删对象。
- `start_prediction` 状态守卫；`finally` 清理临时目录。

### B. 部署
- 生成脚本：det/rec 判别（`TrainModel` 增加逻辑判别或从训练任务推断）；OCR config 由 `mode/model_size` 定；rec 用检测框裁剪；推理超参（conf/iou/imgsz）注入；健康检查。
- 生命周期：`_deploy_running` 从 DB 重建；周期对账容器状态；`stop_deployment`/`delete_deploys` 无论内存与否都停容器；端口选择排除 running/deploying。
- 续期 Key → 重启容器。

### C. 视频推理
- `inference/scheduler`：用 pidfile/DB 记录 worker PID，启动前检测存活，避免重复；health 检查按 PID。
- 规则：解析 `schedule_json`/`sensitivity`/`detect_region`/`interval_seconds` 并下发 worker 配置；worker 应用 ROI/灵敏度。
- 报警：快照存 `DETECTIONS_DIR` 相对名 + HTTP 路由 `/detections/{name}`；类别 id→名称映射；规则匹配纳入 algorithm_task/severity。

### D. 前端
- 预测详情/列表用接口返回的签名 URL；部署页日志/详情查看器；部署表单 det/rec 选择；视频布控时段/ROI 编辑器接线。

## 验收标准

- 批量预测出图且**长期可下载**（重签）；PaddleX 预测参数正确生效。
- 部署启停/续期/健康在**重启后**仍正确（真机 Docker）。
- 视频布控时段/灵敏度/ROI 真实生效；报警图片可显示、可通知。
- 都有 pytest；关键交互有 Playwright；部署/推理关键路径真机验证。

## 实施顺序（拆多个 plan）
1. **3A 批量预测**
2. **3B 部署生命周期与脚本**
3. **3C 视频推理**
4. **3D 前端（预测/部署/布控）**
