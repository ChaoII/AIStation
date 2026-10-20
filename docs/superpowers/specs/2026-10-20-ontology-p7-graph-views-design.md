# P7 顶点：保存视图 + 图模板 + 时间轴 设计（Graph Views）

> 范围：`docs/ontology-gap-analysis.md` 排期表 **P7**（唯一未完成项）——把本体图能力从「能看到」提升到「能存、能分享、能按时间浏览」。
> 三个相对独立的子功能：**保存视图**、**图模板**、**时间轴**。
> 前置决策（已与用户确认）：数据结构用方案一（独立表，复刻对象视图模式）；保存视图按域、模板全局；时间轴基于对象已有时间属性 + 时间滑块过滤。

---

## 1. 背景与目标

当前本体图谱工作区（`OntGraphWorkspace.vue` + `GraphCanvas.vue`，Cytoscape）已支持：对象类型关系图、多步扩展、布局（`cose/concentric/breadthfirst/grid`）、主题、缩放/适配/搜索、多选、最短路径、物理模式、只显示有关联、右键菜单。

但**没有**：把当前图配置保存下来复用、分享给别人、按时间维度浏览。P7 补这三点。

### 1.1 成功标准

- 用户在某个本体域下把当前图（布局/主题/过滤/选中/缩放）保存为「保存视图」，可重新加载、可分享给角色、可看版本历史并回滚、可设为该域默认。
- 用户可把任意图配置存为「图模板」（全局），并随时从模板一键还原。
- 用户在「对象探索」（实例关系图）上选择一个实例的时间属性 + 时间范围滑块，图上淡出不在范围内的实例节点。

### 1.2 非目标（YAGNI）

- ❌ 不引入独立「事件/活动记录」模型（官方 events / time-series 的时间戳模型）——时间轴基于对象已有时间属性。
- ❌ 不做「由图生成应用 / 函数 / 嵌入 Workshop」。
- ❌ 不做图市场（marketplace-vertex）。
- ❌ 不做「链接合并 / 设置控制面板 / 只读模式」（均为 B 级、非核心）。

---

## 2. 数据模型

两张新表，并入 `service._ensure_ontology_schema()` 的 DDL 列表（本项目 `ai_ont_*` 无 Alembic 迁移，运行时幂等建表）。

### 2.1 `ai_ont_graph_view`

```sql
CREATE TABLE IF NOT EXISTS ai_ont_graph_view (
  id BIGSERIAL PRIMARY KEY,
  code VARCHAR(160) NOT NULL,               -- 如 gv_<uuid>
  name VARCHAR(200) DEFAULT '',
  description TEXT DEFAULT '',
  graph_kind VARCHAR(16) DEFAULT 'saved',   -- 'saved' | 'template'
  domain_code VARCHAR(80) DEFAULT '',       -- saved 必填(按域)；template 可空=全局
  state JSONB DEFAULT '{}',                 -- 图配置快照
  filters JSONB DEFAULT '[]',               -- 备用：时间轴初始时间属性/范围
  share_roles JSONB DEFAULT '[]',           -- 空=跟随域权限
  share_mode VARCHAR(16) DEFAULT 'inherit',
  status VARCHAR(24) DEFAULT 'experimental',
  visibility VARCHAR(24) DEFAULT 'normal',
  created_by VARCHAR(120) DEFAULT '',
  is_default BOOLEAN DEFAULT false,
  version INTEGER DEFAULT 1,
  created_time TIMESTAMP DEFAULT now(),
  updated_time TIMESTAMP DEFAULT now(),
  is_deleted BOOLEAN DEFAULT false
)
```

`state` 结构（与 `OntGraphWorkspace` 现有状态对齐）：

```jsonc
{
  "layout": "cose",          // cose | concentric | breadthfirst | grid
  "theme": "default",        // default | ocean | forest | sunset | mono
  "onlyConnected": false,
  "physicsMode": false,
  "shortestMode": false,
  "multiSelect": false,
  "search": "",
  "selected": [],            // 选中对象编码
  "zoom": 1,
  "pan": { "x": 0, "y": 0 }
}
```

### 2.2 `ai_ont_graph_view_version`

```sql
CREATE TABLE IF NOT EXISTS ai_ont_graph_view_version (
  id BIGSERIAL PRIMARY KEY,
  view_code VARCHAR(160),
  version INTEGER,
  state JSONB DEFAULT '{}',
  note TEXT DEFAULT '',
  created_by VARCHAR(120) DEFAULT '',
  created_time TIMESTAMP DEFAULT now()
)
```

> 幂等：用 `CREATE TABLE IF NOT EXISTS`；对存量库用 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` 兜底新增列（如后续需要）。

---

## 3. 后端

### 3.1 模块 `graph_view.py`

新建 `backend/app/plugin/module_ai/ontology/graph_view.py`，**复刻 `object_view.py` 的结构与手法**：

- `_row_to_view(row)`：JSON 列（`state/filters/share_roles`）反序列化包装，避免漏字段（对齐 `object_view._V_JSON_FIELDS` 的坑）。
- 查询/CRUD：`list_views(domain_code, kind)`、`get_view(code)`、`create_view(data, actor)`、`update_view(code, data, actor)`、`remove_view(code)`（软删）、`set_default(code, domain_code)`。
- 版本：`list_versions(code)`、`restore_version(code, version, actor)`（把某版本 state 写回主表，并自增 version）。
- 分享：`share_view(code, share_mode, roles)`、`can_view_view(code, principal)`（按 `share_roles` + 域权限）、`list_shared_views(principal)`、`view_link(code)`（深链）。
- 与对象视图的差异：归属维度是 `domain_code`（域），而非 `object_code`（对象类型）。

### 3.2 路由（`controller.py`，前缀 `/api/v1/ai/ontology`）

路由前缀统一用 `graph-views`（复数，对齐 `object-views` 惯例）；权限沿用 `AuthDep`（只读，`module_ai:ontology:query`）/ `AuthEdit`（写，`module_ai:ontology:edit`）。

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/graph-views` | AuthDep | 列表（按 `domain_code`、`kind` 过滤） |
| GET | `/graph-views/{code}` | AuthDep | 详情（含 state） |
| POST | `/graph-views/save` | AuthEdit | 新建/修改（saved 或 template） |
| POST | `/graph-views/default` | AuthEdit | 设为域默认 |
| POST | `/graph-views/remove` | AuthEdit | 软删 |
| GET | `/graph-views/{code}/versions` | AuthDep | 版本历史 |
| POST | `/graph-views/restore` | AuthEdit | 回滚到某版本 |
| POST | `/graph-views/share` | AuthEdit | 设置 share_mode/share_roles |
| GET | `/graph-views/{code}/link` | AuthDep | 生成深链 |
| GET | `/graph-views/timeline-props` | AuthDep | 时间属性候选（见 3.3） |

`timeline-props` 用 `query` 权限（只读），由 `graph_view.py` 提供给 `object_view`/前端使用。

### 3.3 时间轴只读端点

`GET /graph-views/timeline-props?domain_code=` 返回该域对象类型中**可作为时间轴的属性**候选：

- 逻辑：遍历 `ai_ont_object`（域内）→ `ai_ont_property`，筛出 `base_type` 表示时间/日期的属性。
- 判定集合：`base_type ∈ {"date", "datetime"}`（本项目值类型枚举 `function_engine.ONT_VALUE_TYPES` 含 `date`/`datetime`；实例有 `("sold_at","成交日期","date")`、`("made_at","提出时间","datetime")` 佐证）。实现时若发现还有 `timestamp` 之类取值，追加到该集合即可。
- 返回：`[{ object_code, object_name, prop_code, prop_name, base_type }]`。
- 前端从该端点取候选，供时间轴面板下拉。

### 3.4 权限模型

- 读：`AuthDep`（`module_ai:ontology:query`）+ `can_view_view(code, principal)`（按 `share_roles`；`share_mode='inherit'` 时跟随域权限）。
- 写：`AuthEdit`（`module_ai:ontology:edit`）+ 域编辑权限（复用现有域权限判定）。
- 列表：`list_views` 默认只返回当前主体可见的（继承 `can_view_view`）。

---

## 4. 前端

### 4.1 保存视图 / 图模板（`OntGraphWorkspace.vue`）

- 顶部工具栏靠右加「视图 / 模板」控制区（Element Plus `el-dropdown` + `el-dialog` + `el-form`）。
- 保存：读当前全部图状态 → `POST /graph-views/save`（`graph_kind='saved'`，`domain_code=当前域`）。
- 加载：下拉列出当前域 saved + 全局 template → 还原 `state` 到图工作区（`layout/theme/onlyConnected/selected/search/zoom/pan/...`）。
- 分享：`el-select` 多选角色 → `POST /graph-views/share`；生成深链 `GET /graph-views/{code}/link`。
- 版本：`el-dialog` 列版本 → `POST /graph-views/restore`。
- 设为默认：`POST /graph-views/default`。
- 图模板：单独入口，保存为 `graph_kind='template'`（`domain_code=''` 全局）；「从模板还原」复用上面的加载逻辑。

组件约定：全部使用 `--el-*` 变量、Element Plus 组件；按钮带 `v-hasPerm="'module_ai:ontology:edit'"`（写操作）/ `'module_ai:ontology:query'`（只读）；删除类二次确认（`ElMessageBox.confirm`）。

### 4.2 时间轴面板（对象探索 / 实例关系图）

- 在「对象探索」实例图上加一个可折叠「时间轴」面板（`el-card`）。
- 下拉选时间属性（来自 `timeline-props`）+ 双滑块选范围（`el-slider range`）。
- 图上：实例节点若其选中时间属性值不在 `[start,end]`，则淡出（降低透明度/样式），范围内正常显示。
- 复用现有节点高亮/淡化机制（`highlightNodes` + 节点样式），新增一个「时间过滤淡化集合」。
- 时间值来源：实例真实数据行的时间字段；读取失败容错为「不做淡化」。

---

## 5. 错误处理

| 场景 | 处理 |
|---|---|
| 保存/加载/分享接口失败 | `ElMessage.error`（复用现有，提示后端 msg） |
| `can_view_view` 不通过 | 列表不含该视图；加载/详情节 403 提示 |
| `state` 缺失/非法 JSON | 回退默认图（当前布局/主题），不崩溃 |
| `timeline-props` 无候选 | 面板显示「无可用于时间轴的属性」 |
| 时间值解析失败 | 该节点不做淡化，保持原样 |

---

## 6. 测试

### 6.1 后端（TDD，先写失败测试）

新增 `backend/tests/test_graph_view.py`：

- `TestGraphViewCRUD`：create（saved/template）→ list（按域/kind）→ get → update → remove（软删）。
- `TestGraphViewShare`：share_roles 设置；`can_view_view` 按角色判定；`list_shared_views`。
- `TestGraphViewVersion`：更新自增 version；restore 回滚 state；版本历史。
- `TestGraphViewDefault`：set-default（域内唯一 is_default）。
- `TestGraphViewPermission`：无 edit 权限不能 save/remove（403）。
- `TestGraphViewTimelineProps`：`timeline-props` 返回含时间属性的候选。

`backend/tests/_ont_ddl.py`（SQLite 测试建表）追加 `ai_ont_graph_view` / `ai_ont_graph_view_version` 的 DDL（沿用该文件「按列分别写 CREATE/DELETE」的既有规避）。

### 6.2 前端

- `pnpm run type-check`；改动文件 `eslint` 干净。
- `vitest`：若图工作区/组合式有单测则补充。
- 无头浏览器验证：保存→切走→加载还原 state；创建模板→从模板还原；时间轴面板选属性+滑块后实例节点淡化。

### 6.3 回归

- 后端：`tests/test_ontology*.py`、`tests/test_object_view_index_proposal.py` 无回归。
- 前端：现有本体相关测试不回归（`pnpm run lint` 全量的 48 项既有错误与本任务无关）。

---

## 7. 里程碑

1. 后端：DDL + `graph_view.py` 模块 + 路由 + 权限 + `timeline-props`（TDD 先行，全绿）。
2. 前端：图工作区「保存视图/模板」控制区 + 时间轴面板。
3. 联调与无头浏览器验证。
4. 文档：更新 `docs/ontology-gap-analysis.md`（P7 打勾 + 计数变动）与本 spec。
