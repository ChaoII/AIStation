# Batch B1（云侧）报告：场景目录诚实化 + 启用 obb/iseg

- 分支/基线：`main @ 4afca02`；工作目录 `D:\AIStation`。
- 范围（仅云侧）：`backend/app/api/v1/module_video/scene/**`、`backend/tests/**`（场景/算法）、
  `frontend`（scene API + 规则编辑器）。未触碰 `inference/**`、`edge/**`、`init_app.py`、
  `alembic/**` 与 C++ 仓库。
- 提交：`35225a6`（后端契约 + 目录 + 测试）、`af67a72`（前端原因清单展示），本报告随附提交。
- 验证：`uv run pytest -q` → **871 passed**（基线 865，新增 6 个用例）；
  `uv run ruff check --no-fix`（6 个改动文件）→ All checks passed；
  `pnpm run type-check` → 仅剩既有无关错误（module_generator/monitor/system/task），
  `module_video` 0 错误；`pnpm run e2e -- sp5a-rule-editor` → 2 passed，
  `-- sp6a-rule-scope` → 3 passed（后端 8001 / 前端 5180）。

## 新增契约：`scene/contract.py`

场景可配置性不再逐场景硬编码，而是由「能力契约位 + 求值器叶子实现状态」推导：

| 契约位 | 当前值 | 精确翻转条件 |
|---|---|---|
| `AGENT_MODEL_FAMILIES` | det/cls/**face**/pedestrian_attribute/ocr/lpr/tracking/**obb**/**iseg** | Agent 每落地一族即加入（或在 Agent 改为按编译开关上报后改为运行时读设备能力） |
| `AGENT_EVENT_FEATURES` | 空（不含 `classification`） | **Agent 让分类结果（label_name/attributes）进入事件 sink 后**加入 `"classification"` |
| `AGENT_ASSETS` | 空 | 人脸底库表 + 导入 API + Agent 装载链路就绪后加入 `face_gallery`；跨镜底库就绪后加入 `reid_gallery` |

## 四个事项的落地

1. **「假可配置」修正**：`SCENE_CLS` / `DEFECT_CLS` / `NO_MASK` 增加
   `requires_classification=True`；`scene_configurability` 在
   `not contract.supports_event_feature("classification")` 时据实置灰，原因
   「分类结果未进入边缘事件（等待 Agent 分类契约落地）」。翻转条件为上面的
   `AGENT_EVENT_FEATURES` 位——`test_classification_scenes_flip_when_contract_lands`
   通过 monkeypatch 模拟契约落地，锁定「一旦置位即自动转为可配置且默认规则可编译」。
2. **启用 obb / iseg**：`contract.AGENT_MODEL_FAMILIES` 纳入 `obb`/`iseg`，
   `OBB_DET`/`I_SEG` 转为可配置，默认规则 `object_present` 可编译（测试
   `test_obb_iseg_use_canonical_pipeline_types` 锁定）。目录 pipeline type 统一写
   `obb`/`iseg`；`contract.canonical_pipeline_type` 把旧写法 `seg`/`instance_seg`
   归一为 `iseg`，`test_all_scene_pipeline_types_are_canonical` 防回归。
3. **族名分裂 `face` vs `face_detection`**：规范族名选定为 **`face`**（与 Agent
   `capability.cpp` 上报一致）；`contract.FAMILY_ALIASES` 接受旧别名
   `face_detection`→`face`。目录中 FACE_REC/STRANGER/FACE_ATTR/FACE_ANTISPOOF/
   FACE_LANDMARK 的 `model_families` 由 `face_detection` 改为 `face`（pipeline 的
   模型 type 仍为 Agent 规范名 `face_detection`）。
   `test_face_family_is_canonical_with_legacy_alias` 覆盖三条链路：目录族名、
   目录↔契约能力判定（`is_edge_implementable` 接受旧别名构造的场景）、以及
   Agent 侧归一化约定（`canonical_pipeline_type("face")=="face_detection"`）。
4. **让路线图可见（数据驱动原因）**：新增 `scene_blockers()`，按
   「缺模型族 → 缺外部资产 → 缺分类契约 → 缺求值器叶子」聚合；`/video/scene/catalog`
   在原有 `unsupported_reason` 之外新增结构化 `blockers: list[str]`（schema + controller），
   前端规则编辑器逐条展示。FACE_REC/STRANGER 原因含「缺模型族：face_rec」+「缺外部资产：人脸底库」，
   REID_TRACK 含「缺外部资产：跨镜底库」。

## 测试更新

- `tests/test_scene_edge_support.py`：可落地族含 obb/iseg；不可落地场景 19 → **17**
  （40 场景 / 23 可落地）；目录接口断言 OBB_DET/I_SEG `edge_supported=True`。
- `tests/test_scene_contract_consistency.py`：可配置场景由 21 → **20**
  （+OBB_DET/I_SEG，−SCENE_CLS/DEFECT_CLS/NO_MASK）；新增分类契约门控与翻转、
  obb/iseg pipeline 规范名、全场景 pipeline 规范名、face 族名与旧别名、缺底库原因 5 组用例；
  `test_unconfigurable_scenes_reason_mentions_cause` 扩展为按四类原因分别核实。

## 兼容性

`FACE_DET`、`DET_ZONE`、`GATHER` 等原可配置场景保持可配置；既有规则不受影响
（编译层未改，`object_present`/`text_match` 等叶子行为不变）。已存在的
SCENE_CLS/DEFECT_CLS/NO_MASK 规则仍可加载/保存，只是选择器对新配置置灰并给出原因。

## 关注点 / 待协调（concern）

1. **文件所有权**：`edge/**`、`inference/**` 依约束未改动。因此
   `edge/service.capability_satisfies` 与 `edge/orchestrator.build_agent_task_config`
   未做别名归一化。功能上可行：设备上报的族就是规范名 `face`，目录已改为 `face`；
   Agent 侧 `normalize_model_type` 已把 `face` 归一为 `face_detection`，故人脸链路无需改。
   若需兼容「上报 `face_detection` 的旧设备」，应在 `capability_satisfies` 引入
   `contract.canonical_family` 做双侧归一（2 行改动，位于非本批所有权文件）。
2. **I_SEG 的 Agent 侧 type 名**：`edge/orchestrator._MODEL_TYPE_KEYWORDS` 仍把
   `SEG`→`seg`，而本批规范名为 `iseg`。请并行 Agent 的 `normalize_model_type`
   **同时接受 `seg` 与 `iseg`**（`contract.canonical_pipeline_type` 已提供映射），
   否则 I_SEG 下发可能带 `seg`。已在本报告标注，未越权改 edge。
3. **obb/iseg 默认开启**基于 B1 联调交付；`AGENT_MODEL_FAMILIES` 是代码常量
   （`setting.py` 不在本批所有权内），若并行 Agent 构建尚未真正上报这两族，
   需回退该常量或在设备级能力校验处自然拒绝（下发仍 fail-safe）。
4. 目录可配置性是**全局契约**而非逐设备：逐设备过滤仍由任务创建/下发时的
   `capability_satisfies` 完成（item 4 的「设备上报能力」在设备级体现）。
5. `.superpowers/sdd/progress.md` 与 `docs/issues.md` 为会话前既有改动，未纳入本批提交；
   e2e 重新生成的 2 张 runbook 截图已还原，避免二进制噪声。
