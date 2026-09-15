# SP6-a 规则作用域扩组与跨相机聚合设计

- 日期：2026-09-15
- 上游：`2026-09-14-visual-deployment-program-design.md` §8（SP6 进阶）、`2026-09-15-sp5a-rule-editor-design.md`
- 范围：AIStation 前后端（规则作用域 + 跨相机聚合叶子 + 编辑器作用域选择）

## 1. 背景与现状

| 现状 | 证据 |
|------|------|
| **相机分组已存在** | `CameraGroupModel`（表 `video_camera_groups`）、`CameraModel.group_id` FK、组 CRUD `/video/camera/group/*`、前端 `views/module_video/camera_group/index.vue` |
| **规则是单相机绑定** | `alarm/model.py::AlarmRuleModel.camera_id` 为 `nullable=False` FK |
| 规则只按相机查询、**仅选一条** | `inference/service.py::process_detection_callback` 按 `camera_id + alarm_type` 查规则 → `pick_alarm_rule()` 取一条 |
| 时序状态按相机分桶 | `inference/temporal.py`：键 `ai:temporal:{camera_id}:{alarm_type}:{label}:{scope}`，**无跨相机聚合** |
| 叶子能力由注册表驱动（SP5-a） | `scene/leaves.py::LEAF_CAPABILITIES` + `scene/compile.py::PARAM_TO_LEAF` |

因此"一条规则覆盖多台相机"与"跨相机聚合判定"均无法表达。

## 2. 目标 / 非目标

**目标**

1. 规则作用域支持**相机组**：`camera_id` 变可选 + 新增 `group_id`（二者恰有其一）。
2. 同一事件可命中**多条规则**（直绑 + 组绑），逐条评估、各自节流。
3. 新增跨相机聚合叶子 `group_count` / `group_coverage`，并接入能力注册表与编辑器。

**非目标**

- 跨镜目标关联（reid）。
- 规则间编排/联动（规则引用规则）。
- 规则灰度（SP6-b）、模型热更新（SP6-c）。
- 算法任务扩组（`AlgorithmTask` 仍按单相机下发）。

## 3. 设计

### 3.1 数据模型

`alarm/model.py::AlarmRuleModel`：

- `camera_id`：`nullable=False` → **nullable=True**（FK 不变，`ondelete=CASCADE` 保留；组规则为 NULL）。
- 新增 `group_id: Mapped[int | None]`：`ForeignKey("video_camera_groups.id", ondelete="SET NULL")`，`index=True`。
- **约束**：`camera_id` 与 `group_id` **恰有其一非空**（应用层校验：都空或都填 → 400）。
- 新增 Alembic 迁移；既有规则 `camera_id` 保留，行为不变。

`alarm/schema.py`：`AlarmRuleCreate/Update/Out` 增加 `group_id`，`camera_id` 变可选。

### 3.2 评估：作用域匹配 + 多规则多条告警

`process_detection_callback` 的规则查询改为：

```python
group_id = await _camera_group_id(session, camera_id)      # 相机所属组（可空）
stmt = select(AlarmRuleModel).where(
    or_(
        AlarmRuleModel.camera_id == camera_id,
        and_(AlarmRuleModel.group_id.is_not(None), AlarmRuleModel.group_id == group_id),
    ),
    AlarmRuleModel.alarm_type == alarm_type,
    AlarmRuleModel.status.is_(True),
    AlarmRuleModel.is_deleted.is_(False),
)
```

- **行为变更**：由「`pick_alarm_rule` 选一条」改为**遍历全部匹配规则**，逐条 `_observe_temporal_event` + `explain_conditions`；任一命中即建告警（各自 `interval_seconds` 节流）。单条命中时结果与现状一致。
- 返回体：`rule_matched`（首个命中规则名，兼容）+ 新增 `rule_matched_list`（全部命中规则）。
- 时序观测：同一事件可能对多条规则观测（`_observe_temporal_event` 幂等写入，重复观测同一 `(camera,label)` 无副作用）。
- `pick_alarm_rule` 保留（供其他调用点/兼容），但主路径不再使用其"只选一条"语义。

### 3.3 跨相机聚合叶子

| 叶子 | 契约 | 语义 |
|------|------|------|
| `group_count` | `{"subject":"group_count","label"?,"labels"?,"window_sec":s,"op":">=｜>｜<=｜<｜==","value":n}` | 组内各相机在窗口内的**去重目标**数（按 `(camera_id, track_key)` 去重）与 `value` 比较 |
| `group_coverage` | `{"subject":"group_coverage","window_sec":s,"op":">=｜>｜<=｜<｜==","value":r}` | 窗口内有目标的相机数 / 组内相机总数（比例）与 `value` 比较 |

- **触发**：任一成员相机事件到达即评估；其余相机取各自最近状态。
- **实现**：
  - `_match_conditions` / `explain_conditions` 新增形参 `group_camera_ids: list[int] | None`。
  - `TemporalStore` 新增 `query_multi(camera_ids, alarm_type, label, scope) -> dict`（逐相机 `query()` 合并，键带上 `camera_id` 前缀避免跨相机 track 冲突）。
  - `_eval_temporal` 新增两分支；`TEMPORAL_SUBJECTS` 增加两 subject。
  - `group_camera_ids` 为 `None`/空 → 不命中（组叶子无组上下文时 fail-closed）。
  - `group_coverage` 分母为组内**相机总数**（含离线）；分子为窗口内 `last_seen >= now - window_sec` 的相机数。
- **归属校验**：`group_count`/`group_coverage` **仅允许用于组作用域规则**；相机作用域规则使用 → `compile_rule` 抛 `RuleCompileError`（HTTP 400）。

### 3.4 能力注册表与编译层

- `scene/leaves.py`：`LEAF_CAPABILITIES` 增加 `group_count`（`label`/`labels`/`window_sec`/`value` + ops）与 `group_coverage`（`window_sec`/`value` + ops），`implemented=True`；`IMPLEMENTED_LEAVES` 自动包含 → 对拍测试需同步（`TEMPORAL_SUBJECTS` 亦包含两者）。
- `scene/compile.py`：`PARAM_TO_LEAF` 增加 `window_sec → group_count/group_coverage`、`count/labels → group_count` 的映射；新增作用域校验（组叶子 × 相机规则 → 报错；相机叶子 × 组规则 → **允许**，语义为"组内任一相机命中即命中"）。
- 组规则须携带 `group_id` 上下文；编译校验签名扩展为 `compile_rule(scene_type, params, conditions, *, scope=None)`（`scope ∈ {"camera","group"}`）。

### 3.5 前端

- `RuleEditor`：作用域选择（`单选：相机 / 相机组`）+ 对应选择器（相机下拉 / 相机组下拉，来自既有 `/video/camera/group/list`）；提交时 `camera_id` 或 `group_id` 二选一。
- `alarm/index.vue`：列表/详情展示作用域（相机名 / 组名）；筛选支持按作用域。
- 条件树组件**无需改动**（新叶子由 `rule-capabilities` 自动出现；组叶子仅在作用域=组时的 `fields` 中出现——由前端按 `scope` 过滤 `fields`）。
- 视觉沿用 Element Plus；完成后无头截图 + `vision-recognition` 核对。

### 3.6 非目标（重申）

reid 跨镜关联、规则间编排、灰度、热更新、任务扩组。

## 4. 测试与验收

**后端**
- `tests/test_rule_scope.py`：相机规则不受影响；组规则按组内相机命中；直绑 + 组绑**同时命中两条规则 → 两条告警**；`camera_id`/`group_id` 都空或都填 → 400。
- `tests/test_group_leaves.py`：`group_count` 去重（同相机多 track、跨相机同 track 不误去重）、窗口边界、`op` 各分支、无组上下文不命中；`group_coverage` 比例与分母（含离线相机）。
- `tests/test_rule_compile.py`（扩展）：组叶子用于相机规则 → `RuleCompileError`；相机叶子用于组规则 → 通过；`scope` 形参默认值保持既有调用兼容。
- `tests/test_rule_capabilities.py`（扩展）：新叶子进入注册表且与求值器支持集对拍一致。
- 全量 `uv run pytest -q` + `uv run ruff check`。

**前端**
- `pnpm run type-check`、`pnpm run lint`（本任务文件 0 新增）。
- Playwright e2e：新建**组规则**（选相机组 + `group_count` 叶子）→ 保存 → 组内相机构造事件 → 断言告警出现且作用域显示为组名。
- 无头截图 + `vision-recognition` 核对。

**真机**
- 两台相机（同一视频源模拟）加入同一相机组 → 下发各自单相机任务 → 触发组规则聚合告警 → 前端可见；随后还原环境。

## 5. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 多规则多条告警改变既有语义 | 单条命中时行为不变；用测试锁定；返回体保留 `rule_matched` 并新增 `rule_matched_list` |
| 跨相机聚合的"去重"歧义（不同相机的 track_id 独立） | 去重键为 `(camera_id, track_key)`——文档明确"跨相机同 track_id 不视为同一目标" |
| 组内相机过多导致评估变慢 | 聚合只读时序键；限制单组相机数上限（如 64）并在编译期校验 |
| 组规则误用相机叶子/反之 | 编译层作用域校验（400）+ 单测 |
| 组被删除 | FK `ondelete=SET NULL` → 组规则作用域失效（评估不到）；列表提示"未绑定组" |
| 时序状态按相机分桶不变 | 聚合只在评估期做，不新增跨相机写路径（避免竞态） |

## 6. 兼容性

- 既有相机规则：`camera_id` 仍为主路径，行为与结果不变（除"同相机同类型多条规则"场景从"取一条"变为"全部评估"）。
- `compile_rule` / `_match_conditions` / `explain_conditions` 新增形参均有默认值（`scope=None`、`group_camera_ids=None`），既有调用点不受影响。
- 新增迁移仅涉及 `video_alarm_rules`（改 `camera_id` 可空 + 加 `group_id`）。
- 不新增第三方依赖。
