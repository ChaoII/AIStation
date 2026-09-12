# Phase 6 全量回归验收报告

> 日期：2026-09-13
> 范围：全流程（标注→训练→评估→预测→部署→视频/协作）自动化回归 + 矩阵真机抽验状态

## 1. 环境

- 操作系统：Windows；Shell：PowerShell 7
- Docker：`29.5.3`（daemon 可用）
- 本地镜像：`ultralytics/ultralytics:latest`、`paddlex:latest`、`rustfs/rustfs:latest`、`postgres:17`、`redis:latest`（另有多版本）
- 后端：`http://127.0.0.1:8001`（uvicorn reload，dev）
- 前端：`http://127.0.0.1:5180`（Vite dev）
- DB/Redis/对象存储：Postgres + Redis + RustFS（dev）

## 2. 自动化回归结果

### 2.1 后端 pytest

命令：`cd backend && uv run pytest -q`

结果：**278 passed**（4 warnings；warnings 为既有 deprecation）。

新增/相关测试：
- `test_snapshot_url.py` / `test_snapshot_route.py`（快照路由与归一化）
- `test_alarm_rule_match.py` / `test_alarm_snapshot_url.py`（告警规则与出参）
- `test_train_dataset_name.py`（训练/评估名称 enrich + 预测 name 搜索）
- `test_export_history.py`（导出历史写入）
- `test_annotation_rollback.py`（标注回滚新建版本）
- `test_collaboration_ws.py`（协作 WS 鉴权/presence）
- `test_inference_worker.py`（旧 3C worker 加固）

### 2.2 前端类型与静态检查

- `vue-tsc --noEmit`：**新增/改动文件 0 错误**；项目级存在 16 条 pre-existing 错误（`module_generator/module_monitor/module_system/module_task`），与本次无关。
- `eslint`/`prettier`：Phase 3D/4/5A/5B 新增与改动文件均 clean（`LivePlayer.vue`、`annotation/task`、`record` 的残留为 pre-existing）。

### 2.3 前端 E2E（Playwright）

新增用例（均可在隔离运行下通过）：

| 用例 | 覆盖 |
|---|---|
| `edge.spec.ts` | 边缘设备页 |
| `deploy-edge-roi.spec.ts` | 布控页设备选择 + ROI |
| `alarm-snapshot.spec.ts` | 告警快照列 |
| `train-to-eval.spec.ts` | 训练→评估闭环自动开窗 |
| `repo-to-predict.spec.ts` | 仓库→预测预填 |
| `dataset-to-train.spec.ts` | 数据集→训练预填 |
| `export-history.spec.ts` | 导出历史抽屉 |
| `deploy-log.spec.ts` | 部署详情/日志抽屉 |
| `train-schedule.spec.ts` | 定时训练 Tab 弹窗 |
| `clean-drawer.spec.ts` | 数据清洗抽屉 |
| `annotation-history.spec.ts` | 标注历史抽屉 |
| `repo-versions.spec.ts` | 仓库版本抽屉 |
| `collaboration.spec.ts` | 协作在线指示 |

**全量套件结论**：受长时运行的 dev 后端 DB 连接池（`QueuePool limit of size 10 overflow 20`）耗尽与前端 10s 客户端超时影响，`pnpm e2e` 全量运行时个别既有/新增用例（如 `smoke`、`stats`、`clean-drawer`、`train-to-eval`）会间歇失败；等待连接池回收后逐项复跑均通过。**判定为环境负载问题，非代码回归**（失败点均为请求超时，非断言逻辑）。

## 3. 矩阵真机抽验状态

| 类型 | Ultralytics | PaddleX | 状态 |
|---|---|---|---|
| 检测 | ☐ | ☐ (det) | 待人工真机执行 |
| 分割 | ☐ | — | 待人工真机执行 |
| 旋转框 | ☐ (OBB) | — | 待人工真机执行 |
| 关键点 | ☐ (pose) | — | 待人工真机执行 |
| 分类 | ☐ (cls) | ☐ (mlcls) | 待人工真机执行 |
| OCR-det | — | ☐ | 历史已验（SP2：官方权重 MSE 1.68e-11；det eval hmean） |
| OCR-rec | — | ☐ | 历史已验（SP2：GTC 权重 strict-load；字符 acc） |

说明：真实"少 epoch 训练→评估→预测→部署"单条链路耗时以小时计，且依赖 GPU 调度；本次会话以自动化回归为主，矩阵真机链路按上述清单由人工在具备 GPU 的环境执行，命令与产物路径遵循 PROGRAM Phase 6 与各 Phase 计划。前端/后端主链路的等价自动化已在 2.1-2.3 覆盖。

## 4. 已知问题与遗留

- 开发后端长时运行后 DB 连接池耗尽（`QueuePool`），建议 e2e 前重启后端或调大池。
- 协作房间为进程内内存，多 worker 不共享（Redis 化待办）。
- 协作标注同步采用 last-write-wins 重载，无 CRDT 合并；远端光标仅广播未精确渲染。
- 项目级 vue-tsc 16 条与 ruff FAST002 若干为 pre-existing。
- 导出历史下载依赖 presigned URL 有效期。

## 5. 结论

- 后端单测/集成：**278 passed**，绿色。
- 前端新增特性 E2E：**逐项通过**；全量套件受环境负载波动，需在稳定后端（重启/扩池）下复跑确认。
- 矩阵真机：OCR det/rec 历史已验证；其余类型待人工真机抽验。
- 程序 Phase 0-5（含 3C/3D/4/5A/5B）功能与自动化回归均已完成并提交。
