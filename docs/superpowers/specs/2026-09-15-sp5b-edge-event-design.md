# SP5-b 边缘事件落库与实时可视化设计

- 日期：2026-09-15
- 上游：`2026-09-14-visual-deployment-program-design.md` §8（SP5 前端）、`2026-09-15-sp5a-rule-editor-design.md`
- 范围：AIStation 前后端（事件表/接口/WS + 前端实时流页面）

## 1. 背景与现状

| 现状 | 证据 |
|------|------|
| 边缘事件**不落库**：消费后仅内存去重，命中即建告警 | `backend/app/api/v1/module_video/edge/consumer.py::_process_payload`（去重 + 调 `process_detection_callback`），无持久化 |
| 前端 `event` 模块是「事件联动」配置，**不是**边缘事件流 | `frontend/src/api/module_video/event.ts`（create/update/delete/list 联动规则） |
| 告警只保留命中时刻的 `ai_result.detections`，**不含"哪个叶子命中"** | `inference/service.py::process_detection_callback` 返回 `{alarm_id, alarm_created, rule_matched}` |
| 事件 v2 已含 objects/attributes/text/track_id，但**无处可查** | `edge/consumer.py::normalize_edge_event` |

因此无法回溯"设备上报了什么"、也无法解释"规则为什么命中/没命中"。

## 2. 目标 / 非目标

**目标**

1. 落库边缘事件（**只落有检测的事件**），支持分页/筛选/详情查询。
2. 落库时记录**命中叶子**，可视化"规则为什么命中"。
3. WebSocket 实时推送新事件到前端；前端提供实时流 + 筛选 + 详情抽屉 + 命中高亮。
4. TTL 清理，避免无限增长。

**非目标**

- 告警快照叠加绘制（SP5-c）。
- 跨相机/多规则组合（SP6-a）、规则灰度（SP6-b）、模型热更新（SP6-c）。
- 事件删除/导出、事件重放。

## 3. 设计

### 3.1 数据模型

新表 `video_edge_events`（`app/api/v1/module_video/edge/model.py`）：

| 列 | 类型 | 说明 |
|----|------|------|
| `id` | int PK | |
| `event_id` | str(64) 唯一 | Agent 事件 UUID（**幂等键**） |
| `edge_code` | str(64) | 边缘设备码 |
| `camera_id` | int | 相机 |
| `task_id` | int | 布控任务 |
| `algorithm_type` | str(64) | 场景码 |
| `ts` | DateTime(tz) | 事件时间（由 `frame_timestamp` 归一化） |
| `objects` | JSONB | v2 对象数组（含 attributes/text/track_id） |
| `detections` | JSONB | 兼容数组 |
| `latency_ms` | float | |
| `snapshot_ref` | str(512) null | 快照引用（不存内联 base64） |
| `matched` | bool | 是否命中规则 |
| `matched_rule_id` | int null | 命中规则 |
| `matched_leaves` | JSONB | 命中叶子描述列表 |
| `created_time` | DateTime | 入库时间 |

索引：`event_id` unique；`(camera_id, id)`、`(algorithm_type, id)`、`(matched, id)`、`(ts)`。

- **只落有检测的事件**：`objects` 与 `detections` 皆空（静默期心跳）→ 不落库。
- **幂等**：`event_id` 唯一约束；插入冲突（`ON CONFLICT DO NOTHING` 语义）视为重复，跳过。

### 3.2 写入点

在 `inference/service.py::process_detection_callback` 内落库（它同时持有归一化检测与命中规则，内聚且 MQTT/HTTP 两路共用）：

1. 空检测（静默期心跳）→ **一律不落库**（无论规则是否时序、无论是否触发 absence 告警；此类告警仍由 `alarm_record` 记录）。
2. 有检测的事件：命中/未命中**均落库**（未命中也需可回溯"为什么没命中"）。
3. 返回体增加 `event_id`，供 consumer 日志关联。
4. 落库失败仅告警，不阻断告警链路（与原快照保存失败策略一致）。

### 3.3 命中叶子 explain

`inference/service.py` 新增：

```python
def explain_conditions(conditions, detections, *, temporal=None, camera_id=None,
                       alarm_type=None, now=None, alarm_interval=0) -> tuple[bool, list[dict]]:
    """在 _match_conditions 的同一求值语义下，额外返回命中的叶子路径。"""
```

- 复用既有 `eval_leaf` / `eval_node`：把内部求值改为"返回 `(bool, hits)`"，`hits` 元素形如
  `{"path": "and/0", "subject": "object_present", "label": "person", "detail": "person>=0.4"}`。
- `_match_conditions(...)` 改为调用 `explain_conditions(...)[0]`，**对外行为与返回类型不变**（既有测试必须全绿）。
- `not` 节点：内部命中集合作为其 children 的命中集合（负向语义在 `detail` 里标注 `negated`）。
- 时序叶子（`dwell`/`count_window`/`absence`/`line_cross`）命中时 `detail` 带关键量（如 `dwell: t:3 12s>=10s`）。

### 3.4 接口

| 接口 | 说明 |
|------|------|
| `GET /video/edge/event/list` | 分页（`page_no/page_size`）+ 筛选：`camera_id`/`task_id`/`algorithm_type`/`matched`/`start_time`/`end_time`/`keyword`（objects 文本/label 模糊） |
| `GET /video/edge/event/detail/{id}` | 全量 `objects`/`detections`/`matched_leaves` |
| `WS /api/v1/video/edge/event/ws?token=<jwt>` | 实时推送：`{"type":"event", "data": <detail>}` |

- list/detail 权限 `module_video:edge:query`（与既有 edge 接口一致）。
- WS 鉴权：query 参数 token（浏览器 WS 无法带自定义头），校验失败即关闭（`4401`）。
- 广播：落库后经 **Redis pub/sub**（频道 `ai:edge:event`）发布；WS 端点在进程内订阅该频道并转发（多进程安全；Redis 不可用时降级为进程内 bus）。

### 3.5 TTL 清理

`app/api/v1/module_video/edge/retention.py`：

```python
async def purge_old_events(retention_days: int = 30) -> int: ...
```

- 启动时跑一次 + 每 1 小时一次的 asyncio 任务（挂在既有启动流程，随应用生命周期启停）。
- `retention_days` 由 `settings.EDGE_EVENT_RETENTION_DAYS`（默认 30）控制。

### 3.6 前端

新增 `frontend/src/views/module_video/event_stream/index.vue` + `src/api/module_video/edge_event.ts`：

- 顶部筛选：相机、场景（`getSceneCatalog`）、是否命中、时间范围、关键字。
- 视图切换：「实时」（WS 追加，滚动上限 200 行，可暂停/继续、可清屏）｜「历史」（`list` 分页）。
- 表格列：时间、相机、场景、目标数（label 摘要）、延迟、命中标记（tag）。
- 行点击 → 详情抽屉（`el-drawer`）：检测框列表（label/置信度/track_id/属性/文本）、`matched` 与 `matched_rule_id`、**命中叶子高亮标签**（`matched_leaves`）、快照引用链接。
- 与既有模块风格一致（Element Plus + `--el-*`）；完成后无头截图 + `vision-recognition` 核对。
- 新增菜单项（`sys_menu` 插入 + admin 角色授权，按 AGENTS.md 菜单注册流程）。

## 4. 测试与验收

**后端**
- `tests/test_edge_event_store.py`：空事件不落库；幂等（同 `event_id` 两次只一条）；命中/未命中均落库并带 `matched_leaves`；`snapshot_data` 不入库（仅 ref）。
- `tests/test_explain_conditions.py`：各叶子命中路径正确；`and`/`or`/`not` 语义；时序叶子 detail；`_match_conditions` 与 `explain_conditions` 判定完全一致（对拍）。
- `tests/test_edge_event_api.py`：list 分页/筛选、detail 404、权限。
- `tests/test_edge_event_ws.py`：Redis pub/sub 广播 → WS 收到（fakeredis）；鉴权失败关闭。
- `tests/test_edge_event_retention.py`：超期删除、未超期保留。
- 全量 `uv run pytest -q` + `uv run ruff check`。

**前端**
- `pnpm run type-check`、`pnpm run lint`（仅本任务文件无新增问题）。
- Playwright e2e：登录 → 事件页 → 历史模式展示（造一条事件）→ 打开详情 → 断言命中叶子标签可见。
- 无头截图 + `vision-recognition` 视觉核对。

**真机**
- 起 Agent（MQTT）播含目标视频 → 事件落库 → 前端「实时」页在 <2s 内出现该事件 → 详情含 objects 与命中叶子。

## 5. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 事件量导致表膨胀 | 只落有检测事件 + 30 天 TTL + 复合索引 |
| WS 多进程广播不一致 | Redis pub/sub；不可用降级进程内 bus（并告警） |
| WS 鉴权（浏览器无法带头） | query token + 失败即关连接；仅推只读事件数据 |
| `explain_conditions` 改动影响既有判定 | 对拍测试：`_match_conditions` 结果与 `explain_conditions()[0]` 必须逐例一致 |
| 落库失败影响告警 | try/except 包裹，仅告警日志 |
| `snapshot_data` 撑爆行 | 只存 `snapshot_ref`，内联 base64 丢弃 |

## 6. 兼容性

- `process_detection_callback` 对外返回体仅**新增** `event_id` 字段；既有 `alarm_created`/`rule_matched`/`reason` 语义不变。
- `_match_conditions` 签名与返回类型不变（内部改为调用 `explain_conditions`）。
- 新表为增量；不迁移历史数据（历史事件本就未保存）。
- 菜单为新增项，既有菜单不变。
