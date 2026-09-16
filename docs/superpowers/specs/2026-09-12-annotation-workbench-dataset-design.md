# Phase 1：标注工作台 + 数据集 设计

> 创建日期：2026-09-12
> 状态：已确认（用户认可范围与关键决策）
> 所属程序：`2026-09-11-pipeline-optimization-program-design.md`

## 背景

数据标注是端到端主链路的起点。审查发现标注工作台与数据集存在多处会导致**数据损坏或丢稿**的缺陷，且这些缺陷会沿"导出 → 训练"链路放大。本 Phase 聚焦"标注 → 数据集 → 导出/导入"这一段的正确性。

## 范围

**做（主链路正确性）：**
1. 标注任务进度/状态真实落库（含状态机与 `completed_at`）。
2. 工作台首图自动加载。
3. 图片锁定与保存冲突（硬锁 + 409，不丢稿）。
4. 导出格式正确性：X-AnyLabeling、YOLO（det/seg/obb/pose/cls）、PaddleOCR（det+rec）。
5. 导入健壮性：zip-slip、stem 冲突、计数重算、任务类型推断、类颜色。
6. 统计页 422 与统计语义修正。
7. 任务类定义、备注字段、批量启用/停用接线。

**不做（归入 Phase 5）：**
- 实时协作 WS（光标/焦点/多人实时）
- 数据清洗 / 异常检测 UI
- 导出历史 UI
- 标注版本历史/回滚 UI（Phase 1 仅保证版本写入正确）

## 关键决策（已确认）

| 决策点 | 结论 |
|---|---|
| 协作实时 / 数据清洗 / 导出历史 / 版本回滚 UI | Phase 5 |
| 图片锁语义 | **硬锁**：他人已锁则该图只读；保存冲突返回 409；支持续租与离开解锁 |
| 导出验收矩阵 | YOLO det/seg/obb/pose/cls + PaddleOCR det/rec + X-AnyLabeling，全部要求能被对应官方工具重新导入 |
| 进度落库 | 任务 `progress`/`status`/`completed_at` 由服务真实写入；前端不再自行伪造 |

## 组件设计

### A. 任务进度与状态机（后端）
- `TaskService.update_progress()` 使用可提交会话写入 `progress`/`status`/`completed_at`。
- 状态机：`pending → in_progress → completed`；进度 = 已标注图片数 / 总数（分母排除软删图片）。
- 列表接口避免每行开新会话的 N 次查询（批量计算）。

### B. 工作台（前端 `module_annotation/annotation/index.vue`）
- 首图加载条件修正（`currentImage` 判空逻辑）。
- 锁定：进入图片先取锁；被他人锁定 → 该图只读并提示；保存前校验锁归属；冲突 409 → 不覆盖、提示并保留本地编辑。
- 类编辑（新增/删除/改名）标记未保存并可保存；保存错误不再被 `catch {}` 吞掉。
- 空标注保存的本地状态与后端一致（不误标 `annotated`）。

### C. 导出（后端 `module_train/exporter.py`）
- **X-AnyLabeling**：输出像素坐标；覆盖 AxisAlignedBox/RotatedBox/Polygon/Keypoint/OCR/Classification；类名取真实 label。
- **YOLO**：
  - det/seg 保持现有格式但修正类 id 映射（连续化，避免越界）。
  - OBB 用合法格式（8 角点或正确的 `cls cx cy w h angle`，角度统一为刻度）。
  - pose 输出补 `kpt_shape`/`flip_idx` 到 `dataset.yaml`。
  - cls 支持单/多标签目录与 label 格式。
- **PaddleOCR**：det 与 rec 可同时导出（输出目录分别为 `det/`、`rec/`）；det 纳入 AxisAlignedBox 与 Ocr 四边形；rec 使用官方 `ppocrv6_dict`。

### D. 导入（后端 `x_anylabeling_importer.py`）
- 解压防 zip-slip；按 `(相对路径, stem)` 避免同名覆盖；导入后按实际形状推断任务类型；重算 `image_count`/`annotated_count`；类分配稳定颜色。

### E. 统计（`module_annotation/stats`）
- 前端 `page_size` 收敛到后端 `le=100`；`overview`/数据集下拉不再因 `Promise.all` 失败而全空。
- `annotated` 语义与工作台一致；`user_contributions` 的"标注数"口径修正。

### F. 任务元数据
- 创建任务时可定义类别（`classes`）；`description` 落库；批量启用/停用接入后端 setter。

## 验收标准

- 标注→保存后，任务 `progress`/`status`/`completed_at` 真实落库，统计数字与详情一致。
- 6 种形状导出后，可被对应官方工具重新导入且坐标/类名/形状不丢失。
- 锁冲突有明确 409，用户本地编辑不丢失。
- 无筛选/有筛选统计页均正常渲染，`page_size` 合法。
- 都有 pytest 覆盖；关键交互有 Playwright 用例。

## 实施顺序（建议拆多个 plan）
1. **1A 导出/导入格式正确性**（数据损坏最严重，先做）
2. **1B 工作台：首图/保存/锁定冲突/类编辑**
3. **1C 进度与状态机 + 统计 + 任务元数据**
