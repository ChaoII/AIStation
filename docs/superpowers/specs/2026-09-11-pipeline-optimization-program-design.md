# 全流程优化程序设计（标注 → 训练 → 评估 → 预测 → 部署）

> 创建日期：2026-09-11
> 状态：待用户评审

## 背景与目标

AIStation 的数据标注、模型训练/评估、模型预测/部署/视频推理全流程经逐文件审查，发现 **200+ 条具体缺陷**，其中高严重度（功能不可用 / 数据损坏 / 安全隐患）约 40 条。典型问题包括：

- 标注任务进度/状态从不落库；首图不自动加载；图片锁形同虚设导致丢稿。
- 数据集导出格式错误（归一化坐标写进 X-AnyLabeling、YOLO OBB 非法、OCR det/rec 互斥、类名丢失）。
- 定时训练 100% 失败；PaddleX 训练被误判失败；后端重启后训练/推理容器变孤儿。
- 评估关联错模型 id；评估只评 20% 随机数据；OCR 指标前端不显示。
- PaddleX 预测参数全丢；部署重启后停不掉真实容器；OCR 部署对整图识别。
- 视频模块所有删除接口 body 格式不符 → 全 422；报警快照无 HTTP 路由。
- 端到端 `训练→评估`、`eval 导出`、`数据集→训练` 等跳转断裂；全站重复 toast。

**目标**：把上述全流程从"看似有、实际用不了"修复为"真实可用、无大量 bug"，并统一界面体验。全部标注类型（检测/分割/旋转框/关键点/分类/OCR）与全部框架（Ultralytics / PaddleX det+rec）都要能走通。

## 已确认的关键决策

| 决策点 | 结论 |
|---|---|
| 首要目标 | 先打通端到端主链路（标注→训练→评估→预测→部署），验收以真实跑通为准 |
| 类型/框架范围 | 全部标注类型 × 全部框架（Ultralytics + PaddleX det/rec）均为验收范围 |
| 验证环境 | 本机环境完整：Docker + GPU + PostgreSQL + Redis + 对象存储；本地已有镜像（`ultralytics/ultralytics:latest`、`paddlex:latest`、`rustfs/rustfs:latest` 等）与数据，可真机端到端验收 |
| 非主链路半成品功能 | 全部修到可用（不删除、不长期隐藏） |
| 交付方式 | 方案 A：按子系统纵向切片，逐个 spec→plan→实现→验证；先做底座 |
| 自动化测试 | 引入浏览器自动化（Playwright）作为前端 E2E 护栏；后端以 pytest 为主 |

## 总体架构

```
Phase 0  基础设施与数据一致性        ← 底座，先做
Phase 1  标注工作台 + 数据集
Phase 2  模型训练 + 模型评估
Phase 3  模型预测 + 部署 + 视频推理
Phase 4  端到端串联 + UI/UX 统一
Phase 5  非主链路半成品功能补全
Phase 6  全量回归验收（6 类型 × 2 框架）
```

依赖关系：Phase 0 是所有后续工作的前提；Phase 1/2/3 相对独立但按顺序推进更稳；Phase 4 依赖 1-3；Phase 5 最后补半成品；Phase 6 收口。

**每个 Phase 独立走一次完整流程，各自产出一份独立 spec 与 plan；本文件是程序级（program-level）设计，Phase 0 的详细设计在本文件第 5 节，其余 Phase 在各自 spec 中细化。**

## 横切原则

1. **根因优先**：不靠 `try/except` 掩盖、不靠 `!important` 堆样式、不改测试迁就 bug。
2. **契约优先**：后端 Pydantic schema 与前端 TS 类型对齐，消除大面积 `any`；接口变更同步两端。
3. **统一执行器基类**：训练/评估/预测/部署的容器生命周期、孤儿恢复、取消、日志跟随统一到 `TaskExecutor` 基类，恢复靠容器标签（label）而非内存注册表。
4. **删除语义一致**：明确每张表软删/物理删，级联关系写清楚；软删除模型一律补 `is_deleted` 过滤。
5. **UI 统一规范**：所有页面统一使用 `EnhancedDialog` + `PageSearch`/`PageContent`；统一空/加载/错误态；统一 toast 策略（只由一处负责成功/失败提示）。
6. **可验证**：每个修复尽量补 pytest；前端补 Playwright E2E；每 Phase 结束做真机端到端并记录。
7. **不引入新 bug**：小步提交，每步可回退；重构与修 bug 分开提交。

---

## 第 5 节（Phase 0）：基础设施与数据一致性

### 5.1 要解决的问题

| # | 问题 | 证据位置 |
|---|---|---|
| 0.1 | `module_train` 与标注图片写入绕过 `CRUDBase`，`updated_id`/`deleted_id`/软删除永不写 | `plugin/module_train/service.py`，`module_annotation/dataset/service.py:52-59`；`docs/issues.md` #1/#2 |
| 0.2 | 删除不级联：删数据集/任务后图片、标注记录、导出记录成孤儿 | `core/base_crud.py:318-336` |
| 0.3 | Alembic 迁移漂移：`train_tasks.annotation_task_id`/`cleanup_delay_minutes`、`train_models.repo_id`/`export_format`、`train_evals.progress` 等在 ORM 但不在迁移、启动补列也漏 | `alembic/versions/b744384adf6f_*.py`，`scripts/init_app.py:563-572` |
| 0.4 | 视频模块所有删除接口 body 为 `{ids:[...]}`，后端声明裸数组 → 422 | `frontend/src/api/module_video/*.ts` vs `module_video/*/controller.py` |
| 0.5 | 推理依赖 `modeldeploy`/FastDeploy 未在 `pyproject.toml`/`requirements.txt` 声明，开箱即挂 | `module_video/inference/registry.py:21` |
| 0.6 | 枚举字符串比较 bug：`str(TrainFramework.PADDLEX).lower()` = `"trainframework.paddlex"` | `plugin/module_train/task_executor.py:130`，`paddlex_executor.py:59-60` |
| 0.7 | 全局拦截器与页面双重弹成功/失败 toast | `utils/request.ts:69-77` + 各页面 |
| 0.8 | 前端完全无测试框架（无 Playwright/Cypress/vitest） | `frontend/package.json` |
| 0.9 | S3 客户端所有操作默认 `env="dev"`，prod 数据落 dev bucket | `utils/s3_client.py:26-58` |
| 0.10 | 权限/菜单只种一次：`module_train:model:update` 从未注册；`TrainTaskDetail` 不在补全列表 | `scripts/init_app.py:356-393` |

### 5.2 设计

**A. 数据访问层统一**
- 为 `module_train` 与标注图片引入统一的审计写入助手（`created_id`/`updated_id`/`deleted_id` 与软删除），或改造为调用 `CRUDBase`；二选一，倾向抽一个 `AuditMixin`/`set_audit()` 小工具，避免大改绕过逻辑。
- `CRUDBase.delete()` 增加级联钩子：数据集删除时级联软删图片/记录；任务删除时级联处理标注记录。
- 明确并文档化每张表的删除语义（软/硬）。

**B. 数据库迁移一致性**
- 重新生成一份完整 Alembic 迁移，覆盖所有 ORM 字段；验证"空库 create_all"与"旧库 upgrade"最终 schema 一致。
- 在 `_ensure_missing_columns` 中补齐漏掉的新列作为兜底。
- 增加一个启动期 schema 自检（开发环境告警）。

**C. 接口契约修复**
- 视频模块所有删除调用统一为裸数组 body（与后端一致），全模块排查。
- `module_video` controller 加参数校验与 404 语义（详情不存在返回 404 而非 `data=None`）。

**D. 依赖与运行时**
- 显式声明/安装推理依赖；若 `modeldeploy` 无法安装，则实现可插拔后端 + 明确降级错误（不静默 `model_load_failed`）。

**E. 全局提示策略**
- 统一由请求拦截器负责成功/失败提示；页面移除重复 `ElMessage`；提供 `_silent` 选项处理需要自定义提示的少数场景。

**F. 浏览器自动化基础**
- `frontend` 引入 Playwright（Chromium）+ 脚本：`pnpm e2e`（起后端 + Vite 预览 + 跑用例）。
- 提供登录态复用、测试数据 seed 约定、失败截图/trace。
- 建立 `e2e/` 目录与第一批"冒烟"用例（登录、进入各模块页面无报错）。

**G. 权限/菜单补全**
- 补种 `module_train:model:update` 等缺失权限；把 `TrainTaskDetail` 等加入补全列表。
- 增加"菜单/权限 reconcile 清单"机制，避免只在空库种数据。

### 5.3 验收标准

- 旧库执行 `upgrade` 后，ORM 全字段存在且可读写；空库与升级库 schema 一致。
- 视频模块增删改查全部 200；删除正确的行。
- 上传/训练/评估/预测/部署后，`created_id`/`updated_id` 正确写入；删除后软删字段正确。
- 任意操作只弹一次提示。
- `pnpm e2e` 能跑通登录 + 各页面冒烟。
- 推理依赖可导入，或在不具备时给出明确可读错误而非静默失败。

---

## Phase 1：标注工作台 + 数据集

**核心问题**：进度/状态不落库（session 未 commit）；协作 WS 无鉴权且一用即崩、前端未接入；导出格式数据损坏（归一化坐标、丢形状、丢类名、det/rec 互斥、OBB 非法）；图片锁仅前端提示、后端 400 拒绝保存 → 丢稿；首图不自动加载；统计页 `page_size:999` 触发 422 整页空；导入 zip-slip 与计数错误；任务类定义/备注字段断链；标注历史/数据清洗接口无 UI。

**范围**：标注工作台（画布工具/撤销重做/保存与自动保存/锁与冲突 409）、数据集（上传/导入/导出 6 类型全格式正确性）、标注任务（进度、状态机、assign 权限、类定义）、统计、协作实时、数据清洗/异常检测 UI、导出历史。

**验收**：标注→保存→进度/状态真实落库；6 种形状可正确导出为对应格式且能被官方工具重导入；锁冲突明确 409 且不丢稿；统计数字与详情一致；协作实时可用且有鉴权。

## Phase 2：模型训练 + 模型评估

**核心问题**：定时训练必失败（缺 `base_model_id`）；PaddleX 误判失败、孤儿恢复不执行；重启后容器孤儿、取消竞态、删任务不停容器；各框架指标解析不全（cls/OCR）、best 指标策略分裂；评估只评 20% 随机数据、不可复现；评估关联错模型 id；评估详情只显示 YOLO 指标；导出无产物仍标成功；仓库双套数据模型（`TrainModelRepo` vs `TrainModel`）不一致；`base_model_id` 从不被读取。

**范围**：训练调度与执行器（恢复/取消/删除/并发/GPU）、各框架命令与指标、评估链路（模型解析、全量可复现、指标展示）、模型仓库/版本/导出/下载、训练与评估前端（列表/详情/图表/WS）。

**验收**：det/seg/OBB/pose/cls/OCR-det/OCR-rec 均能训练出产物；重启后可恢复或正确回收；取消/删除不留孤儿容器；评估可复现且指标按框架正确显示；仓库/版本/导出下载一致。

## Phase 3：模型预测 + 部署 + 视频推理

**核心问题**：PaddleX 预测用多个 `-o` 导致参数全丢；结果存签名 URL 会过期且不清理存储；部署注册表仅内存，重启后停/删不停真实容器；OCR 部署对整图识别、配置硬编码 `small`；部署缺 det/rec 判别、缺日志/详情 UI；视频推理依赖没装、worker 重启重复、布控时段/灵敏度/ROI 形同虚设；报警快照无 HTTP 路由、规则匹配不完整、类别显示为数字；视频模块删除 422。

**范围**：批量预测（源/模型解析/执行/结果长期可用）、部署（脚本/生命周期/端口/续期/健康/日志）、视频推理（调度/绑定/资源/时段/ROI/报警/通知）、对应前端页面与结果查看器。

**验收**：批量预测出图并可长期下载；部署启停/续期/健康在重启后仍正确；视频布控时段/灵敏度/ROI 真实生效；报警图片可显示、可通知。

## Phase 4：端到端串联 + UI/UX 统一

**核心问题**：`训练→评估` 死链（按钮是桩）；eval 导出按钮 `v-model` 未接；模型下拉默认只 20 条；`数据集→训练` 无入口、模型→训练不预填、`base_model_id` 无表单字段；编辑表单字段错位（`dataset_id` vs `annotation_dataset_id`、`trainRatio` vs `train_ratio`）；列表显示 ID 而非名称；指标标签不随框架；重复提示；残留自定义 Grid / 非标准 `@media` / 死代码。

**范围**：跨页快捷跳转与上下文预填（数据集→训练、模型→评估/预测/部署、训练→评估、eval→predict）；统一对话框/空态/加载态/确认；术语与字段统一；清理死代码与样式坑。

**验收**：任一列表页都能带上下文跳到下一步；全流程无重复提示；UI 一致；`pnpm type-check`/`lint` 通过。

## Phase 5：非主链路半成品功能补全

**范围**：实时协作（鉴权 + 前端接入 + 光标/焦点）、定时训练 UI、数据清洗/异常检测 UI、导出历史、模型仓库分组/版本 UI、视频布控 schedule UI、部署日志/详情查看器、标注历史/回滚 UI。

**验收**：上述功能均可从 UI 完整操作并产生正确结果。

## Phase 6：全量回归验收

**矩阵**：`{检测, 分割, 旋转框, 关键点, 分类, OCR-det, OCR-rec}` × `标注→训练(小数据/少 epoch)→评估→预测→部署健康检查`。使用本地现成镜像与已有数据。

**产出**：验证报告（每条链路的命令、产物路径、指标、健康检查结果、截图/日志），关键路径补 pytest 回归，前端补 Playwright E2E。

---

## 测试与验收策略

| 层 | 手段 | 命令/说明 |
|---|---|---|
| 后端单测/集成 | pytest | `cd backend && uv run pytest` |
| 后端静态 | ruff | `uv run ruff check` |
| 前端类型 | vue-tsc | `pnpm type-check` |
| 前端静态 | eslint+prettier+stylelint | `pnpm lint` |
| 前端 E2E | Playwright（Phase 0 引入） | `pnpm e2e`（Chromium，真实点击关键流程） |
| 真机端到端 | Docker + GPU + 本地镜像/数据 | 每 Phase 结束按矩阵抽验 |

## 风险与缓解

- **体量巨大**："全类型全框架 + 全部功能修到可用"是多周工程量。缓解：方案 A 分 Phase，每步可验收；每个 Phase 内部按需再拆子 spec。
- **无前端测试历史**：Phase 0 建立 Playwright 护栏，后续每 Phase 补用例。
- **训练/推理数值正确性**：OCR det/rec 与各任务类型的指标正确性需真机核对；用本地已有数据 + 小数据子集快速迭代。
- **重构引入回归**：改 bug 与重构分开提交；每步跑 pytest/type-check/lint；关键链路真机复验。
- **现有 DB 与历史数据**：优先保证迁移可平滑升级，不破坏已有数据。

## 实施顺序（Program Level）

1. Phase 0 底座（本文件第 5 节，第一份 spec + plan）
2. Phase 1 标注 + 数据集
3. Phase 2 训练 + 评估
4. Phase 3 预测 + 部署 + 视频推理
5. Phase 4 端到端串联 + UI/UX
6. Phase 5 半成品补全
7. Phase 6 全量回归

每个 Phase 完成即测试 + 人工验收，验收通过后再进入下一 Phase。
