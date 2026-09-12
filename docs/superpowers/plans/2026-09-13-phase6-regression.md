# Phase 6：全量回归验收 计划

> 目标：以 `{检测, 分割, 旋转框, 关键点, 分类, OCR-det, OCR-rec} × 标注→训练(小数据/少epoch)→评估→预测→部署健康检查` 矩阵做端到端验收，并固化自动化回归。

## 约束

- Docker + GPU + 本地镜像（`ultralytics/ultralytics:latest`、`paddlex:latest`、`rustfs/rustfs:latest` 均已存在）。
- 后端 `uv run pytest`；前端 `pnpm e2e`。
- 真实训练/部署运行耗时长，按条目抽验并记录命令/产物/指标/健康检查。

## 自动化回归清单

- [ ] 后端全量 pytest（`cd backend && uv run pytest -q`）
- [ ] 前端类型检查 `pnpm type-check`（仅判断新增）
- [ ] 前端目标文件 lint
- [ ] 前端全量 E2E `pnpm e2e`

## 矩阵抽验清单（真机）

对每个类型/框架：
1. 造小数据集（≤20 图）并完成标注导出；
2. 建训练任务（少 epoch）→ 轮询至 success 且产出 `best` 权重；
3. 评估 → 指标按框架展示；
4. 预测 → 出图/结果可下载；
5. 部署 → 容器启动 + 健康检查通过。

| 类型 | Ultralytics | PaddleX |
|---|---|---|
| 检测 | ☐ | ☐ (det) |
| 分割 | ☐ | — |
| 旋转框 | ☐ (OBB) | — |
| 关键点 | ☐ (pose) | — |
| 分类 | ☐ (cls) | ☐ (mlcls) |
| OCR-det | — | ☐ |
| OCR-rec | — | ☐ |

## 产出

- `docs/superpowers/reports/2026-09-13-phase6-regression-report.md`：命令、产物路径、指标、健康检查结果、已知问题。
