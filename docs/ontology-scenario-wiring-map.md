```yaml
status: 已完成 (2026-10-19)
commits: [e6754422 后端接线, f2a7c8cf 实例探索器, 8acaa8dc 端到端证明, 8c7b822e 对象视图切换器, e41a1bfb 动作对话框]
e2e: frontend/e2e/scenario-e2e.spec.ts (建场景→场景内执行→编辑数>0→合并后真实表变化)
remaining: instance_aggregate 的场景支持(需把场景差异下推进 SQL, 已改为显式拒绝)
```

# 本体场景（Scenario）链路接线图 —— 第四批实施依据

> 2026-10-19 调查产出。后端沙箱/读时叠加/单事务合并**已经写完**，
> 整个场景功能目前是「空转」：建场景、看 diff、点合并，编辑数永远 0，
> 因为**没有任何入口能产生场景编辑**，读接口也没传 scenario。

## 一、后端现状（已核实）

### 已支持 `scenario`（不用改）

| 端点 | 位置 | 说明 |
|---|---|---|
| `GET /instances/{code}` | `controller.py:697` | 有 `scenario` query 参数，转 `scenario_code=scenario` |
| `GET /instance/{code}/{key}` | `controller.py:714` | 同上 |
| `POST /action/execute` | `controller.py:579` | `scenario_code=str(data.get("scenario",""))` |

service 侧对应：`instance_search`（叠加于 `service.py:2780-2786`）、
`instance_get`（`:2853-2864`）、`execute_ontology_action` 的场景分支（`:1366-1405`
只写 `ai_ont_scenario_edit`、返回 `staged=True`）。

### 缺口（要改）

| 位置 | 现状 | 要做什么 |
|---|---|---|
| `controller.py:721` `/instance/{code}/{key}/pivot` | 签名只有 `code,key,auth,link_id,limit` | 加 `scenario: str = ""`，转 `scenario_code` |
| `controller.py:733` `/instance/graph` | body 取 `object_code/key/link_ids/depth` | 加 `scenario`，转 `scenario_code` |
| `service.py:3108` `instance_pivot(...)` | 无 scenario 参数 | 加参数并在取"对侧实例"时走叠加 |
| `service.py:3166` `instance_graph(...)` | 无 scenario 参数 | 同上；另外它内部调 `instance_get` 时**没传 principal**（既有问题，顺手修） |
| `service.py` `instance_aggregate(...)` | **收了 `scenario_code` 却从头到尾没用** | 图表/聚合在场景里仍显示基线数据 |

### 场景读叠加的现成实现（直接复用，别重写）

- `scenario.overlay_edits(scenario_code, object_code, items)` —— `scenario.py:351-390`
- `scenario.overlay_instance(...)` —— `:393-406`
- `scenario.is_deleted_in_scenario(...)` —— `:409-414`
- 接入范例（照抄这两个）：`service.py:2780-2786`（instance_search）、
  `service.py:2853-2864`（instance_get）

## 二、前端现状（要改）

`frontend/src/api/module_ai/ontology.ts`：

| 函数 | 行 | 现状 |
|---|---|---|
| `searchOntInstances` | 60 | params 无 `scenario` |
| `getOntInstance(code,key)` | 75 | 无 scenario 入参 |
| `pivotOntInstance` | 78 | 无 scenario 入参 |
| `getOntInstanceGraph` | 83+ | 无 scenario 入参 |
| `executeOntAction` | 416 | 无 scenario 入参 |
| `renderOntObjectView(code,key,scenario="")` | 450 | **已有**，但唯一调用点 `OntObjectViewPanel.vue:629` 只传两个参数 |

## 三、UI 接线点（建议顺序）

1. **`OntInstanceExplorer.vue`**：顶部加「场景」下拉（选项来自 `getOntScenarios()`，
   默认"主本体"）。选中后把 `scenario` 传给 `searchOntInstances` / `getOntInstance` /
   `pivotOntInstance` / `getOntInstanceGraph` / `executeOntAction`。
   - 现有调用点：`:380` search、`:431/:502` get、`:473` pivot、`:513` graph、`:601` execute
2. **动作执行对话框**：`OntActionTypeView.vue:850`、`OntObjectTypeView.vue:1195`
   两处调 `executeOntAction`，同样带上当前场景。
3. **场景面板** `OntScenarioView.vue`：现在只能建壳。补一个「进入场景编辑」入口 ——
   打开 `OntInstanceExplorer` 并预设场景，或在场景详情里列已暂存编辑（后端
   `GET /scenario/{code}` 已返回 `edits`，前端 `:239-248` 已在渲染）。
4. **对象视图** `OntObjectViewPanel.vue:176-181`：现在的"场景"是只读 `el-alert`
   提示，改成可切换的下拉并传给 `renderOntObjectView`。

## 四、必写的回归测试（先 RED 再 GREEN）

1. `instance_pivot` 带 scenario 时读到的是叠加后的对侧实例（不是基线）
2. `instance_graph` 同上
3. `instance_aggregate` 带 scenario 时聚合的是叠加数据（当前它收了参数不用）
4. 前端 e2e：建场景 → 在场景内改一行 → 场景编辑数 > 0 → 合并后真实表变化

## 五、已知的相邻问题（顺手修或单独修）

- `instance_graph` 不传 principal ⇒ 根节点绕过行策略（P2-1，审查报告已列）
- `instance_pivot` 在 `principal is None` 时跳过 `filter_instances` ⇒
  派生属性/聚合函数可聚合到无权查看的行（P2-1）
