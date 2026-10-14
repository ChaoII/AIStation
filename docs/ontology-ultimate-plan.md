# 本体（Ontology）模块终极建设计划

> 版本：v1.0 ｜ 依据：Palantir Foundry 官方文档 56 页原始正文 + 10 张官方界面截图（逐张读图核对）
> 适用范围：`backend/app/plugin/module_ai/ontology/`、`backend/app/plugin/module_ai/query/`、`frontend/src/views/module_ai/ontology/`

---

## 0. 证据基础（先说清"凭什么"）

### 0.1 资料来源

| 类别 | 位置 | 数量 |
|---|---|---|
| 官方原始 Markdown 正文 | `.research/palantir/raw/foundry__*.md` | 56 页 |
| 官方界面截图（已逐张读图） | `docs/assets/palantir-ontology/` | 10 张 |
| 类型系统结构化笔记 | `docs/_palantir/notes/A-类型系统.md` | 789 行 |
| 应用与治理结构化笔记 | `docs/_palantir/notes/B-应用与治理.md` | 1357 行 |
| 调研报告 | `docs/_palantir-ontology-research.md` | 1144 行 |
| 抓取工具 | `.research/palantir/fetch-doc.ps1` | 可复现 |

**关键取数方法**：palantir.com/docs 是 Next.js 静态生成站，页面正文完整存放在 `__NEXT_DATA__` → `props.pageProps.markdown` 字段。直接抓 HTML 只能拿到导航壳（这就是之前正文"被挤掉"的原因），必须解析该字段才能拿到全文。该站不存在路径也返回 HTTP 200，但正文长度恒为 262659 字节且 markdown 为空——据此区分"真有这页"与"假 200"。

### 0.2 环境限制（如实声明）

本机网络**只能访问 `palantir.com` 与 `github.com`**。`web_search` 无 API key；`blog.palantir.com` 返回 403；google / duckduckgo / medium / wikipedia / r.jina.ai 全部不可达。

**因此：本计划没有任何第三方来源做交叉验证，全部结论来自官方文档正文与官方截图。** 凡涉及第三方验证的点，文中标注「需外部核实」。

### 0.3 两处必须承认的错误更正

| 我在上一轮的说法 | 事实 | 更正 |
|---|---|---|
| "「本体可视化」（类型层元模型图）在 Palantir 里**不对应任何产品**，是个自造物" | **错。** 对象类型的 Overview 页第 4 分区官方就叫 `Link types`，画的正是"当前对象类型居中、周围是关联对象类型"的**类型层关系图** | 我们这个视图**方向是对的**，只需要补齐布局切换、边方向、样式配置 |
| "Palantir 的图（Vertex）画的是实例关系" | 对，但不完整——**类型层图与实例层图两者都有**，分属 Ontology Manager 与 Vertex | 我们的「本体可视化」（类型层）与「图谱」（资产层）之外，**还缺实例层图** |

### 0.4 官方文档自身的矛盾（未替官方取舍，并列记录）

1. 首页侧边栏两版截图不一致（截图里有 `Health issues` / `Cleanup`，文档正文未提）
2. 动作类型第二页文档写 `Logic`，截图写 `Rules`
3. 链接类型文档称 2 个页面，截图实为 4 个
4. 属性元数据文档称面板有 "four tabs"，截图实为 5 个页签
5. 外键支持的基数：正文写 `one-to-one` + `many-to-one`，同页与元数据页写 `one-to-one` + `one-to-many`
6. API name 校验规则三处不一致（仅字母数字 / 含下划线 / 须合法 Unicode）
7. 截图里可见 `Archetypes` 页签，全部文档零覆盖

---

## 1. 结论先行

### 1.1 一句话诊断

**我们的本体是"平铺的三个清单 + 两个抽屉层级"，而 Palantir 的是"一个容器 + 若干从属分区 + 每个资源自带子导航"。三元素之所以在界面上看不出来，是因为包含关系被画反了。**

### 1.2 核心错位（有像素级证据）

Palantir 的 Ontology Manager 首页左栏（官方截图 `02-oma-homepage-sidebar.png` 实测）：

```
Overview
Search results        137
Object types            5
  └ Properties         19   ← 缩进！属性是对象类型的子项
Link types              1
Action types           20
Shared properties       0
Interfaces              0
Functions             111
Health issues       1,941
Cleanup
History
Advanced
```

而我们的界面：

| 元素 | Palantir | 我们 | 判定 |
|---|---|---|---|
| 对象类型 | 资源清单主体 | 主 tab「对象类型」 | ✅ 方向对 |
| **属性** | **缩进在对象类型之下**；对象类型 Overview 第 2 分区 | 降级为「点对象 → 抽屉 → 二级页签」 | ❌ **层级反了** |
| **关系类型** | 与对象类型**并列**的一等资源；同时在对象类型 Overview 第 4 分区以图呈现 | 提到与对象类型并列的主 tab；无对象类型内的图 | ⚠️ 层级对，缺"从属呈现" |
| 动作类型 | 与对象类型并列的一等资源；对象类型 Overview 第 3 分区 | 藏在抽屉里 | ❌ **层级偏低** |

### 1.3 与 Palantir 的结构性差距（不是字段多少，是形态不同）

| 维度 | Palantir | 我们 |
|---|---|---|
| 导航形态 | 左栏**可切换**：未选资源时是资源清单；选中资源后**换成为该资源的子导航**（顶部带 `← Object types` 返回） | 左树恒为「本体」，右侧 8 个平级 tab |
| 资源视图 | 每个资源有自己的多页面视图（对象类型 9 页 / 关系类型 4 页 / 动作类型 9 页） | 无资源级视图，全部塞在抽屉里 |
| 变更模型 | 改动进**工作副本**，右上角 `Save` 才生效，有 `Review edits`（errors/warnings） | 点保存**立即写库**，无审核、无草稿 |
| 类型层图 | 对象类型 Overview 第 4 分区，带布局切换与新建入口 | 有全局元模型图，但无"以某类型为圆心"的视图 |
| 实例层 | Object Explorer（搜索/沿链接跳转/对结果集执行动作）+ Vertex（实例图） | **完全缺失** |
| 元数据 | 对象类型 14 项、属性 13 项、关系类型 11 项 | 对象类型 8 项、属性 10 项、关系类型 7 项 |

---

## 2. Palantir 的完整概念模型（本体资源全景）

### 2.1 官方定义（core-concepts 页原文转述）

> Ontology 是"组织的数字孪生"，把组织的数字资产（datasets 与 models）整合成一个连贯整体，通过把 datasets 与 models 映射为 object types、properties、link types 与 action types 来构建。

| 概念 | 官方定义 |
|---|---|
| **Object type** | 现实世界实体或事件的 schema 定义 |
| **Object** | object type 的单个实例 |
| **Object set** | 多个对象实例的集合 |
| **Property** | object type 的一个特征的 schema 定义 |
| **Property value** | 某个对象上某个属性的值 |
| **Shared property** | 可被多个 object type 使用的属性；统一建模、集中管理元数据 |
| **Link type** | 两个 object type 之间关系的 schema 定义 |
| **Link** | 该关系的单个实例 |
| **Action type** | 用户可一次性对 objects / property values / links 所做的一组变更的 schema 定义，**并包含副作用行为** |
| **Object type group** | 分类原语，帮助搜索与探索本体 |
| **Interface** | 描述 object type 的形状与能力；提供**对象类型多态** |
| **Value type** | 围绕 field type 的**语义包装**，含元数据与约束；增强类型安全与表达力；常见如邮箱、URL、UUID、枚举 |

### 2.2 官方 Dataset ↔ Ontology 类比表（原样收录）

| Datasets | Ontology |
|---|---|
| Dataset | Object type |
| Row | Object |
| Column | Property |
| Field | Property value |
| Join | Link type |

> 这张表是对我们"从数据表导入生成本体"这一设计最强的合法性背书。

### 2.3 类型分类

- **Ontology types**：用于把现实世界域建模成本体（见上表）
- **Data types**：用于表示数据值；官方注明"受 RDF、OWL、XSD 中的类似概念启发"
- **Field types / Base types 是静态定义的，用户不能新建**；**Value types 可在 space 内动态创建**

### 2.4 包含关系（官方结构，像素级核对）

```
Ontology（一个 space 一个）
├── Object type（对象类型）
│     ├── Property（本地属性，至少 1 个）
│     │     └── Base type（基类型；可为 struct → 含若干 field）
│     ├── Shared property（引用，非独占）
│     ├── Keys：Primary key（恰 1 个）/ Title key
│     ├── Backing datasource（0 或 1；无则纯 action 写入）
│     ├── Groups（0..n 分类标签）
│     └── Interfaces（0..n 实现关系）
├── Link type（链接类型，恰好关联 2 个对象类型，可为自链接）
│     ├── 2 个 Side（每侧含 display name / plural display name / API name / visibility）
│     └── Property（链接自身可带属性）
├── Action type
├── Interface（含 interface properties / link type constraints / action type constraints）
└── Object type group（跨对象类型的分类原语）
Space
└── Value type（属于 space，只能在该 space 内使用）
```

### 2.5 关系类型的三种存储方式与基数（官方）

**Join method 三选一**（官方截图 `06-link-type-view.png` 实测，是 Overview 页 `Configuration` 卡片里的三个大按钮）：

| Join method | 说明 |
|---|---|
| **Foreign key** | 一侧持有指向另一侧主键的外键属性 |
| **Dataset** | 用一张 join table 数据集（many-to-many 必需） |
| **Object type** | 用中间 backing object type 承载链接（object-backed link），可附加元数据与受限视图 |

**基数四值**：

| 基数 | 官方行为 |
|---|---|
| `one-to-one` | **仅意图指示，不被强制** |
| `one-to-many` | 外键方式支持 |
| `many-to-one` | 外键方式支持 |
| `many-to-many` | **唯一需要 join table 的方式**，也是唯一支持用户编辑/writeback 的 |

**方向性**：官方强调 link type 有方向，两侧各有独立的 display name / plural display name / API name / visibility。

### 2.6 完整的资源清单（Ontology Manager 首页左栏，官方截图实测）

`Overview` / `Search results` / `Object types`(⊃ `Properties`) / `Link types` / `Action types` / `Shared properties` / `Interfaces` / `Functions` / `Health issues` / `Cleanup` / `History` / `Advanced`

### 2.7 各资源的视图页面（官方截图实测）

**对象类型视图**（左栏 9 页）：
`Overview` / `Properties` / `Security` / `Datasources` / `Capabilities` / `Object views` / `Interfaces` / `Automations` / `Usage`

**对象类型 Overview 页的 7 个分区**（官方编号，截图 `04-object-type-overview-7-sections.png` 实测）：

| # | 分区 | 内容 |
|---|---|---|
| 1 | 元数据 | Plural name / Description / **Aliases** / **Point of contact** / **Contributors** / Ontology / **API name** ‖ Status / **Visibility** / **Index status** / **Edits** / **ID** / **RID** |
| 2 | Properties | 属性列表，带 `Title` / `Primary key` 徽标，右上 `+ New` |
| 3 | Action types | 动作列表，右上 `+ New` |
| 4 | **Link types** | **类型层关系图**：当前类型居中，周围是关联类型；带缩放/适配按钮与 `Create new link type` |
| 5 | Dependents | 左侧按类型分组计数（Workshop 9 / Function 2 / Graph Template 1 / Quiver Dashboard 1 / Use cases 1 / …），右侧为具体依赖项名称 |
| 6 | Data | backing datasource 条目 + 同步时间 + `See all` |
| 7 | Usage | 读数走势图 + `See more` |

**关系类型视图**（左栏 4 页）：`Overview` / `Security` / `Datasources` / `Usage`
Overview 含：头部两侧端点图标与名称 + `Many-to-one link type` + `Actions ▾`；元数据（Ontology / Status / ID / RID）；**`Configuration` 卡片**（Join method 三选一 + 端点与属性选择器 + 可视化连线图）；`Properties` 卡片。

**动作类型视图**（左栏 9 页）：
`Overview` / `Rules` / `Parameters` / `User Interface` / `Capabilities` / `Security & Submission Criteria` / `Automations` / `History` / `Observability`
Overview 含：元数据（Description / **Tool description** / Contributors / Ontology / API name / Status / RID）；**`Action type overview` 卡片 = Input → Rules 双列图**（Input 列是参数，标注对象引用或基础类型；Rules 列是 `Modify 对象` / `Create 对象` + 可写字段）；`Dependents` 卡片。

> **`Tool description`（工具描述）是动作类型的一等元数据字段**——这是把动作暴露给 AI Agent 作工具调用描述用的。**这一条直接命中我们"本体要和 agent 接线"的目标。**

---

## 3. 产品分工（我们该学哪一部分）

| 产品 | 回答的问题 | 我们的对应 | 优先级 |
|---|---|---|---|
| **Ontology Manager** | 怎么建、怎么改、谁能改、影响谁 | 本体页（已有，形态要改） | **P0** |
| **Object Explorer** | 哪些对象符合条件、彼此如何关联、能否批量做事 | 无 | **P3** |
| **Vertex** | 变化沿什么路径影响什么，网络长什么样 | 「本体可视化」是类型层；实例层无 | P3 |
| **Object Views** | 关于**这一个**对象该看到什么、跳哪、能做什么 | 抽屉（部分对应） | P4 |

> `B-应用与治理.md` §5.3 明确指出：**官方文档没有任何一处直接对比 Vertex 与 Object Explorer**，那张差异表是调研归纳而非文档结论。本计划的取舍同理属于工程判断，已标注。

---

## 4. 现状 vs 目标：概念差距总表

图例：✅ 已有 ｜ ⚠️ 部分/近似 ｜ ❌ 缺失

| Palantir 概念 | 我们的现状 | 判定 | 目标阶段 |
|---|---|---|---|
| Ontology（space） | `ai_ont_domain` 本体 | ⚠️ 我们是"分组"，Palantir 是"空间"（1 space = 1 ontology，分私有/共享） | P1 明确语义 |
| Object type | `ai_ont_object`（8 字段） | ⚠️ 缺 12 项元数据 | P1 |
| Property | `ai_ont_property`（10 字段） | ⚠️ 缺 9 项 | P1 |
| Shared property | 无 | ❌ | P5 |
| Link type | `ai_ont_link`（7 字段） | ⚠️ 缺 join_method / 双向命名 / 链接属性 | P1 |
| Action type | `ai_ont_action`（9 字段） | ⚠️ 缺 rules / parameters / submission criteria / side effects / **tool description** | P1 |
| Function | `ai_ont_function`（算术表达式） | ⚠️ Palantir 是 TS/Python 函数，含 functions-on-objects 与 ontology edits | P2 / P5 |
| Object type group | 无（`domain_code` 近似） | ❌ | P5 |
| Interface | 无 | ❌ | P5 |
| Value type | 无 | ❌ | P5 |
| Struct | 无 | ❌ | P5 |
| Base type | `prop_type` 近似 | ⚠️ 取值需对齐 | P1 |
| Derived property | 无 | ❌ | P5 |
| Backing datasource | `source_col` + 物化表 + 导入来源 | ⚠️ 数据有，界面无 | **P1** |
| Title key / Primary key | `name_prop` / `key_prop` | ✅ | — |
| Aliases | 无 | ❌ | P1 |
| Status / Visibility | `enabled` 布尔 | ⚠️ 需三值/三值枚举 | P1 |
| Index status | 无（有 DQ 分可借） | ⚠️ | P1 |
| Writeback / Edits | 无 | ❌ | P4 |
| Dependents | 无 | ❌ | P2 |
| Usage | 无 | ❌ | P3 |
| Health issues | `dq_score` 近似 | ⚠️ | P2 |
| Save / Review edits | 无（直接生效） | ❌ | **P3** |
| History / Restore | `ai_ont_change_log` / `ai_ont_version` 近似 | ⚠️ | P3 |
| Branching | 无 | ❌ | P4 |
| Proposals | `ai_ont_version` 待审批近似 | ⚠️ | P3 |
| Export / Import（JSON 定义） | 「导入本体」是从数据源导入，语义不同 | ⚠️ | P3 |
| Cleanup | 无 | ❌ | P4 |
| **Link type graph（类型层图）** | 「本体可视化」 | ✅ 方向对，缺布局/边方向/样式 | **P0** |
| Vertex（实例图） | 「图谱」其实是资产 KG，非实例图 | ❌ | P3 |
| Object Explorer | 无 | ❌ | **P3** |
| Object Views | 抽屉近似 | ⚠️ | P4 |
| Search（⌘K，跨资源搜索并标明命中字段） | 仅按名称/编码过滤 | ⚠️ | P2 |

---

## 5. 目标信息架构

### 5.1 布局（对齐 Palantir 的"左栏可切换"）

```
┌──────────────────────┬─────────────────────────────────────────────────────────┐
│ [本体：数据表本体 ▾] │  ┌ 对象类型 ────────────────────────────  [保存] [丢弃] ┐│
│                      │  │ [icon] 摄像机表        对象类型 · 1,240 个对象        ││
├──────────────────────┤  │ [分组] 视频域  12   [编辑分组]                        ││
│ Overview             │  └──────────────────────────────────────────────────────┘│
│ Search results    83 │  ┌─ 元数据 ────────────┬─ 状态 ──────────────────────┐  │
│ Object types      83 │  │ 复数名  摄像机表s   │ 状态     Active ▾           │  │
│   └ Properties  1479 │  │ 描述    ...         │ 可见性   Normal ▾           │  │
│ Link types        33 │  │ 别名    camera ×    │ 索引状态 Success            │  │
│ Action types       7 │  │ 联系人  admin       │ 可编辑   Disabled           │  │
│ Shared properties  0 │  │ API 名  VideoCamera │ ID / RID                    │  │
│ Interfaces         0 │  └─────────────────────┴─────────────────────────────┘  │
│ Functions         10 │  ┌─ 属性 37 ──────────┬─ 动作类型 2 ────────────────┐  │
│ Health issues     12 │  │ 名称    [Title]     │ [icon] 修改摄像机名称       │  │
│ Cleanup              │  │ 编码    [Primary]   │ [icon] 标记离线             │  │
│ History              │  └─────────────────────┴─────────────────────────────┘  │
│ Advanced             │  ┌─ 关系类型 6 ────────────────────────────────────────┐│
│                      │  │        [告警记录表]                                  ││
│                      │  │            │                                         ││
│                      │  │  [分组表]─[摄像机表]─[边缘设备表]   [+ 新建关系类型] ││
│                      │  └──────────────────────────────────────────────────────┘│
│                      │  ┌─ 依赖 14 ──────────┬─ 数据源 ────────────────────┐  │
│                      │  │ 智能体 9 / 函数 2   │ video_cameras 已同步 7周前  │  │
│                      │  └─────────────────────┴─────────────────────────────┘  │
└──────────────────────┴─────────────────────────────────────────────────────────┘
       ↑ 未选资源时：资源清单                    选中对象类型后：其 Overview 页
       ↓ 选中资源后：换成该资源的子导航
┌──────────────────────┐
│ ← 对象类型           │   ← 顶部返回
│ [icon] 摄像机表      │
│   37 个属性          │
├──────────────────────┤
│ Overview             │   ← 9 个子页面
│ Properties        37 │
│ Security             │
│ Datasources          │
│ Capabilities         │
│ Object views         │
│ Interfaces           │
│ Automations          │
│ Usage                │
└──────────────────────┘
```

### 5.2 三条硬性结构规则

1. **`Properties` 必须缩进在 `Object types` 之下**（Palantir 的硬证据）
2. **选中资源后左栏整体替换为该资源的子导航**，顶部带 `← 返回资源清单`
3. **对象类型 Overview 必须包含那 7 个分区**，顺序一致

---

## 6. 数据模型扩展设计

> 现有 9 张表：`ai_ont_domain` / `ai_ont_object` / `ai_ont_property` / `ai_ont_link` / `ai_ont_action` / `ai_ont_function` / `ai_ont_version` / `ai_ont_change_log` / `ai_ont_capability`
> 沿用既有约定：**无 Alembic 迁移**，运行时 `CREATE TABLE IF NOT EXISTS` + 尽力而为的 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`；每个 `_ensure_*_schema()` 全 try/except，保证 SQLite 测试可跑。

### 6.1 P1 阶段字段扩展

```sql
-- 对象类型：+12 项
ALTER TABLE ai_ont_object ADD COLUMN IF NOT EXISTS plural_name TEXT DEFAULT '';
ALTER TABLE ai_ont_object ADD COLUMN IF NOT EXISTS api_name TEXT DEFAULT '';
ALTER TABLE ai_ont_object ADD COLUMN IF NOT EXISTS aliases JSONB DEFAULT '[]';
ALTER TABLE ai_ont_object ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'experimental';   -- active|experimental|deprecated
ALTER TABLE ai_ont_object ADD COLUMN IF NOT EXISTS visibility TEXT DEFAULT 'normal';     -- normal|prominent|hidden
ALTER TABLE ai_ont_object ADD COLUMN IF NOT EXISTS index_status TEXT DEFAULT 'not_started'; -- success|failed|not_started
ALTER TABLE ai_ont_object ADD COLUMN IF NOT EXISTS edits_enabled BOOLEAN DEFAULT false;   -- Writeback
ALTER TABLE ai_ont_object ADD COLUMN IF NOT EXISTS datasource_id INTEGER;                 -- Backing datasource
ALTER TABLE ai_ont_object ADD COLUMN IF NOT EXISTS backing_table TEXT DEFAULT '';         -- 支撑表名
ALTER TABLE ai_ont_object ADD COLUMN IF NOT EXISTS point_of_contact TEXT DEFAULT '';
ALTER TABLE ai_ont_object ADD COLUMN IF NOT EXISTS contributors JSONB DEFAULT '[]';
ALTER TABLE ai_ont_object ADD COLUMN IF NOT EXISTS rid TEXT DEFAULT '';                   -- 平台唯一标识

-- 属性：+9 项
ALTER TABLE ai_ont_property ADD COLUMN IF NOT EXISTS api_name TEXT DEFAULT '';
ALTER TABLE ai_ont_property ADD COLUMN IF NOT EXISTS base_type TEXT DEFAULT '';           -- 对齐官方 base type 取值
ALTER TABLE ai_ont_property ADD COLUMN IF NOT EXISTS title_key BOOLEAN DEFAULT false;
ALTER TABLE ai_ont_property ADD COLUMN IF NOT EXISTS visibility TEXT DEFAULT 'normal';
ALTER TABLE ai_ont_property ADD COLUMN IF NOT EXISTS edit_only BOOLEAN DEFAULT false;     -- 仅通过 action 填充
ALTER TABLE ai_ont_property ADD COLUMN IF NOT EXISTS value_formatting JSONB DEFAULT '{}';
ALTER TABLE ai_ont_property ADD COLUMN IF NOT EXISTS conditional_formatting JSONB DEFAULT '[]';
ALTER TABLE ai_ont_property ADD COLUMN IF NOT EXISTS render_hint TEXT DEFAULT '';
ALTER TABLE ai_ont_property ADD COLUMN IF NOT EXISTS type_class TEXT DEFAULT '';

-- 关系类型：+8 项
ALTER TABLE ai_ont_link ADD COLUMN IF NOT EXISTS join_method TEXT DEFAULT 'foreign_key';  -- foreign_key|dataset|object_type
ALTER TABLE ai_ont_link ADD COLUMN IF NOT EXISTS api_name TEXT DEFAULT '';
ALTER TABLE ai_ont_link ADD COLUMN IF NOT EXISTS source_name TEXT DEFAULT '';
ALTER TABLE ai_ont_link ADD COLUMN IF NOT EXISTS source_plural_name TEXT DEFAULT '';
ALTER TABLE ai_ont_link ADD COLUMN IF NOT EXISTS target_name TEXT DEFAULT '';
ALTER TABLE ai_ont_link ADD COLUMN IF NOT EXISTS target_plural_name TEXT DEFAULT '';
ALTER TABLE ai_ont_link ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'experimental';
ALTER TABLE ai_ont_link ADD COLUMN IF NOT EXISTS visibility TEXT DEFAULT 'normal';

-- 动作类型：+7 项
ALTER TABLE ai_ont_action ADD COLUMN IF NOT EXISTS tool_description TEXT DEFAULT '';      -- ★ Agent 工具描述
ALTER TABLE ai_ont_action ADD COLUMN IF NOT EXISTS rules JSONB DEFAULT '[]';              -- 规则：create/modify/delete object、create/delete link、function rule
ALTER TABLE ai_ont_action ADD COLUMN IF NOT EXISTS parameters JSONB DEFAULT '[]';         -- 参数：对象引用/基础类型、必填、默认值
ALTER TABLE ai_ont_action ADD COLUMN IF NOT EXISTS submission_criteria JSONB DEFAULT '[]';
ALTER TABLE ai_ont_action ADD COLUMN IF NOT EXISTS side_effects JSONB DEFAULT '[]';       -- 通知/Webhook/触发调度构建
ALTER TABLE ai_ont_action ADD COLUMN IF NOT EXISTS ui_sections JSONB DEFAULT '[]';
ALTER TABLE ai_ont_action ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'experimental';
```

### 6.2 P3 / P5 阶段新增表

| 表 | 对应概念 | 阶段 |
|---|---|---|
| `ai_ont_link_property` | 链接自身的属性 | P1 |
| `ai_ont_type_group` + `ai_ont_object_group_rel` | Object type group（多对多） | P5 |
| `ai_ont_shared_property` + 引用关系 | Shared property | P5 |
| `ai_ont_value_type` | Value type（含 constraints / versions / permissions） | P5 |
| `ai_ont_struct` + `ai_ont_struct_field` | Struct | P5 |
| `ai_ont_interface` + `ai_ont_interface_impl` | Interface | P5 |
| `ai_ont_derived_property` | Derived property（含聚合、多跳 ≤3） | P5 |
| `ai_ont_object_view` | Object Views | P4 |
| `ai_ont_branch` / `ai_ont_proposal` / `ai_ont_saved_change` | Branching / Proposals / 工作副本 | P3 |
| `ai_ont_health_issue` | Health issues（也可纯派生计算） | P2 |

### 6.3 派生（不建表，实时计算）

- **Index status**：由最近一次同步/物化结果推导
- **Dependents**：反查其他模块对本体资源的引用（智能体的 `capabilities`、工作流节点等）
- **Usage**：由 `ai_call_log` / `ai_action_log` 统计
- **Health issues**：由既有 DQ 分 + 缺主键 + 无注释 + 孤儿属性等规则推导

---

## 7. 分期实施计划

### P0 — 信息架构纠正（让三元素可见）

**目标**：把包含关系画对。不改数据模型，纯前端 + 少量取数。

| 交付物 | 说明 |
|---|---|
| 左栏双模式 | 未选资源 = 资源清单（Object types ⊃ Properties / Link types / Action types / Shared properties / Interfaces / Functions / Health issues / Cleanup / History / Advanced + 计数）；选中资源 = 该资源子导航 + `← 返回` |
| 对象类型 Overview 页 | 严格实现官方 7 分区顺序（元数据 / Properties / Action types / Link types 图 / Dependents / Data / Usage） |
| 对象类型其余子页 | Properties（正式页面，不再是抽屉二级页签）/ Security / Datasources / Usage |
| 关系类型视图 | Overview（含 `Configuration`：Join method 三选一 + 端点属性选择器 + 连线图）/ Security / Datasources / Usage |
| 动作类型视图 | Overview（Input → Rules 双列图）/ Rules / Parameters / Security & Submission Criteria |
| 类型层关系图增强 | 以某对象类型为圆心 + 缩放/适配 + 布局切换 + `新建关系类型` 入口 |
| 移除抽屉 | 对象详情由"抽屉"升级为"资源视图" |

**验收标准**
1. 左栏可见 `Properties` 缩进于 `Object types` 之下
2. 点击对象类型后，左栏整体切换为该类型子导航，顶部有返回
3. 对象类型 Overview 的 7 个分区顺序与官方一致
4. 属性在 1 次点击内可达（当前为 3 次：点对象 → 开抽屉 → 切页签）

**工作量**：前端重写为主，约 3–4 天。

#### ✅ P0 完成记录

**已交付**
- 左栏双模式：资源清单（`对象类型 ⊃ 属性` / 关系类型 / 动作类型 / 共享属性 / 接口 / 函数 / 健康检查 / 清理 / 历史 / 高级 + 计数徽标）⇄ 资源子导航（顶部「返回」）
- 对象类型视图：Overview 官方 7 分区 + Properties / Security / Datasources / Usage 四个子页；抽屉已移除
- 关系类型视图：Overview（元数据 + **Configuration：Join method 三选一 + 两端属性选择器 + 连接示意**）/ Security / Datasources / Usage
- 动作类型视图：Overview（元数据 + **Input → Rules 双列图**）/ Rules / Parameters / Security & Submission Criteria
- 类型层关系图组件（以某对象类型为圆心，含缩放/适配/5 种布局/新建关系类型入口）
- 跨资源搜索页（对象类型 / 属性 / 关系类型 / 动作类型 / 函数，标明命中项）

**新增文件**
| 文件 | 作用 |
|---|---|
| `ontology/composables/useOntologyData.ts` | 模块级单例共享数据层（domains/objects/links/actions/functions + 作用域过滤 + 健康检查派生） |
| `ontology/components/OntObjectTypeView.vue` | 对象类型视图（7 分区 + 4 子页） |
| `ontology/components/OntLinkTypeView.vue` | 关系类型视图 |
| `ontology/components/OntActionTypeView.vue` | 动作类型视图 |
| `ontology/components/OntTypeLinkGraph.vue` | 以类型为圆心的关系图 |

**验收实测（Playwright，全部通过）**
| 验收项 | 实测结果 |
|---|---|
| 1. `Properties` 缩进于 `Object types` 之下 | 对象类型 `indent:20px` → **属性 `child:true, indent:32px`**，紧邻其后 |
| 2. 选中资源后左栏切换 + 返回 | 左栏变为 `[概览,属性,安全,数据源,能力,对象视图,接口,自动化,使用量]`；「返回」回资源清单 |
| 3. Overview 官方 7 分区顺序 | `["元数据","属性","动作类型","关系类型","依赖","数据源","使用量"]` —— 完全一致 |
| 4. 属性 1 次点击可达 | 点一次「属性」→ 20 行属性表（原为 3 次点击） |
| 关系类型视图 | Join method 三选一（外键/连接表/中间对象）+ 2 个端点选择器 |
| 动作类型视图 | Input → Rules 双列图（列头「输入 Input」「规则 Rules」） |

**P0 期间的额外修复（超出计划但与验收直接相关）**
1. **补上了 `ai_ont_*` 全部 9 张表的运行时建表入口**。此前这些表只在开发库中手工创建，**代码里没有建表语句，新环境部署会直接失败**。现统一收敛到 `_ensure_ontology_schema()`，并作为列演进的唯一入口。
2. 新增 `ai_ont_link.join_method` 列（P0 的 Join method UI 需要；原计划放在 P1）。
3. `list_properties` 支持不传 `object_code` 时列出全部（资源清单「属性」页需要）。
4. 修正：直接以 `uvicorn main:create_app` 启动时必须显式设 `ENVIRONMENT=dev`，否则配置回落到 MySQL 默认值导致启动失败（这是本次踩到的坑，已记录）。

**偏离计划之处（已执行，需知悉）**
- 加了 `join_method` 一列（原计划 P0「不改数据模型」）。理由：Join method 三选一是 P0 验收内容，不落列只能做成假 UI。

---

### P1 — 类型元数据完备（让每个概念完整）

**目标**：对象类型 14 项、属性 13 项、关系类型 11 项、动作类型对齐官方配置面。

| 交付物 | 说明 |
|---|---|
| DDL 扩展 | §6.1 全部字段 + `ai_ont_link_property` 表 |
| 后端 | 各 `_ensure_*_schema()` 扩展；`upsert_*` 支持新字段；`enrich_ontology_semantics` 自动回填 `plural_name` / `api_name` / `base_type` / `aliases` |
| 前端表单 | 元数据分区按官方字段排布；枚举用 `el-select` 固定取值 |
| 状态与可见性 | `status` 三值 / `visibility` 三值，列表可筛选、可排序 |
| Backing datasource 分区 | 显示支撑数据源、表名、字段映射、同步时间 |
| API name 生成 | 由 `code` 自动推导 PascalCase，带唯一性校验 |
| Index status | 由同步/物化结果推导并展示 |
| 跨资源搜索 | 顶部搜索框（对齐 ⌘K），命中字段高亮 |

**验收标准**
1. 逐字段核对：对象类型/属性/关系类型/动作类型的字段数与官方元数据参考表一致
2. 枚举取值与官方一致（status / visibility / index_status / cardinality / join_method）
3. 必填校验生效（对象类型：ID、显示名、复数名、API 名、至少 1 个属性、必须有主键与标题键）
4. 关系类型可表达三种 join method；many-to-many 强制要求 join table

**工作量**：全栈，约 5–7 天。

#### ✅ P1 完成记录

**已交付字段（实测接口返回）**

| 类型 | 字段数 | 新增字段 |
|---|---|---|
| 对象类型 | **26** | plural_name / api_name / aliases / status / visibility / index_status / edits_enabled / datasource_id / backing_table / point_of_contact / contributors / rid |
| 属性 | **22** | api_name / base_type / title_key / visibility / edit_only / value_formatting / conditional_formatting / render_hint / type_class / status |
| 关系类型 | **16** | join_method / api_name / source_name / source_plural_name / target_name / target_plural_name / status / visibility |
| 动作类型 | **17** | tool_description / rules / parameters / submission_criteria / side_effects / ui_sections / status |

**枚举取值（与官方逐项一致）**
- `status`：active / experimental（默认）/ deprecated
- `visibility`：normal（默认）/ prominent / hidden
- `index_status`：success / failed / not_started
- `join_method`：foreign_key / dataset / object_type
- `cardinality`：one_to_one / one_to_many / many_to_one / many_to_many
- `base_type`：16 项官方集合（string…media_reference）

**自动推导与回填（幂等，只填空不覆盖人工值）**
- 对象类型：`plural_name`（中文不加 s）、`api_name`（PascalCase）、`backing_table`、`rid`、`index_status`（由支撑表是否存在推导）
- 属性：`api_name`、`base_type`（由 prop_type 推导）、`title_key`（按对象 name_prop 标记）
- 关系类型：`api_name` —— 关系名多为中文，去掉非 ASCII 会退化，故按**候选序列**取名（名称 → 两端对象 → 两端对象+源字段 → 追加序号），实测 **33/33 唯一、0 空值**

**约束与校验**
- 前端：对象类型必填显示名/编码（复数名与 API 名留空自动推导）；关系类型多对多时连接方式下拉**只允许「连接表 Dataset」**（其余置灰）
- 后端：`upsert_object` 校验 status/visibility 枚举；`upsert_link` 校验 cardinality/join_method 枚举，并**拒绝 many_to_many + 非 dataset 的组合**

**验收实测（Playwright，4 条全过）**
| 验收项 | 实测 |
|---|---|
| 1. 字段数与官方一致 | 元数据分区 **20 个标签**，官方 14 项全部命中；属性表 12 列含 API 名 / Base type / 可见性 |
| 2. 枚举取值一致 | Base type 下拉 16 项官方集合；status/visibility/cardinality/join_method 全部匹配 |
| 3. 必填校验生效 | 空表单保存被拦下并提示「请填显示名与编码」 |
| 4. 多对多强制连接表 | `card=many_to_many` 时：外键 `disabled:true` / 连接表 `disabled:false` / 中间对象 `disabled:true` |

**顺带修复（超出计划）**
1. **`Tool description` 提前落地**（原计划 P2）。它是官方动作类型的一等元数据，且直接服务「本体接 Agent」的目标，故随 P1 一起做了界面与字段。
2. 补上 `ai_ont_*` 全部 9 张表的统一运行时建表入口（P0 期间完成，P1 扩展为列演进的唯一入口）。

**偏离计划之处（已执行，需知悉）**
- 原计划 P1 含 `ai_ont_link_property`（关系自身的属性）。**本次未建该表**：其编辑界面属 P5，先建表会留下无界面的死结构。已把该表挪到 P5。

**已知未做的部分（如实标注）**
- 对象类型的 `Groups` 仍是 1:1（我们的 `domain_code`），官方的 Object type groups 是 0..n 多对多 —— 属 P5
- 属性的 `value_formatting` / `conditional_formatting` 字段已落库，但**没有可视化编辑器**（当前只能通过接口写）
- 动作的 `rules` / `submission_criteria` 字段已落库，但**没有规则编辑器**，且执行器仍只支持「修改对象」一种规则

---

### P2 — Agent 接线增强（用户核心诉求）

**目标**：让本体真正成为 Agent 的能力来源，而不是"只是数据"。

| 交付物 | 说明 |
|---|---|
| `tool_description` 一等字段 | 动作类型与函数都可写"给 AI 看的工具描述"；动作类型 Overview 顶部可见 |
| 动作工具化 | `ont_action__<code>` 工具的 description 优先取 `tool_description`，回退到 `description` |
| 函数 on objects | 函数不再只是算术表达式：支持声明依赖的对象类型/属性，由调用方（Agent）注入实参 |
| 参数 schema 驱动 | 动作的 `parameters`（对象引用/基础类型、必填、默认值、枚举）直接生成工具 JSON Schema |
| 规则校验前置 | 动作的 `rules` 声明可写字段与目标对象，工具调用前即可校验，减少运行期失败 |
| 能力清单 | 一个本体暴露给 Agent 的"能力视图"：哪些对象类型可查、哪些动作可执行、哪些函数可算 |
| 依赖展示 | 对象类型 Overview 的 Dependents 分区显示"被哪些智能体/工作流引用" |

**验收标准**
1. 在界面上给动作写 `tool_description` 后，Agent 工具列表里的 description 随之变化
2. 动作参数在界面上配置后，Agent 工具 schema 自动同步
3. 对象类型的 Dependents 能列出引用了它的智能体
4. 端到端：对 Agent 说一句话 → 命中本体动作 → 走白名单 + 审批门禁 → 写库并留审计

**工作量**：全栈 + Agent 编排，约 4–5 天。

#### ✅ P2 完成记录

**⚠️ 首先修复了一个阻塞性缺陷（否则 P2 无从谈起）**

`ai_agents.capabilities` 这一列**只存在于数据库，模型与 schema 里都没有声明**：

| 位置 | 修复前 | 后果 |
|---|---|---|
| `AiAgentModel` | 未声明该字段 | `getattr(a, "capabilities", None)` 恒为 None → 读出来永远是 `[]` |
| `AiAgentCreateSchema` | 无该字段 | 前端勾选的"本体能力"保存时被丢弃 |
| `AiAgentUpdateSchema` | 无该字段 | 同上 |
| `create()` | 未传该参数 | 新建智能体时能力为空 |

**结论：在本次修复之前，「本体接 Agent」整条链在第一步就是断的**——前端能勾、库里能存（早前手工写的），但运行时读不到，因此既不会生成任何本体工具，多智能体编排也永远匹配不到智能体。三处一并补齐后实测通过。

**已交付**

| 交付物 | 说明 |
|---|---|
| `capabilities` 贯通 | 模型 + 两个 schema + `create()`；实测 `/ai/agents/list` 能读出 5 个本体能力编码 |
| `tool_description` 驱动工具描述 | 动作与函数均支持；工具 description 优先取它，回退 `description`，再回退结构化摘要 |
| 参数 schema 驱动 | `parameters` 声明（key/label/type/required/description/options）→ 工具 JSON Schema；动作回退 `input_schema` → 白名单；函数回退表达式变量 |
| 函数参数声明 | `ai_ont_function.parameters` + `tool_description` 两列；界面上可编辑，并校验"表达式变量必须在参数中声明" |
| 调用前预校验 | 白名单 / 必填参数 / update 必须带主键；把运行期失败提前成可读错误 |
| 能力清单过滤 | `ontology_catalog_text` 与工具构建均排除 `hidden` 与 `deprecated` |
| Dependents 接智能体 | 新增 `GET /ontology/object/{code}/dependents`；对象类型 Overview 的依赖分区列出引用它的智能体及命中编码 |
| 编排语义打通 | 多智能体编排原先只认 `query`/`grounding` 功能标志，现把"挂载了本体能力"也视为具备数据问答能力 |

**验收实测**

| 验收项 | 实测结果 |
|---|---|
| 1. tool_description 驱动工具描述 | 写入后工具 description = `把摄像机改成新名称。当用户要求重命名某台摄像机时调用。` |
| 2. 参数驱动工具 schema | `ont_action__cam_rename`：required=`['object_key','name']`，properties 同；函数按表达式变量推断出 `['online_count','total_count']` |
| 3. Dependents 列出智能体 | `智能体1 问数助手（cam_online_rate）`；接口 `total=10 agents=1` |
| 4. 端到端 | 提议→执行→审计：执行返回 `已写回并留痕`，审计记录 `noop`；白名单拦截返回 `以下字段不在动作白名单内：rtsp_url_main` |
| 附加：可见性过滤 | 动作设为 `hidden` 后从可暴露集合消失（`['cam_mark_offline']`），恢复后回归 |
| 附加：编排匹配 | `intent=query agents_involved=1 → 问数助手` |

**P2 期间发现并修复的其它缺陷**
1. `upsert_action` **从未写入 `visibility`**（P1 加了列但漏了 UPDATE/INSERT）——动作的隐藏过滤实际失效
2. `ai_ont_action` **根本没有 `visibility` 列**（P1 给对象/属性/关系都加了，漏了动作）
3. `_ACT_COLS` 未 SELECT `visibility`，即使有列也读不到

**已知未做的部分（如实标注）**
- 端到端验收走的是「提议 → 执行 → 审计」的确定性链路；**未经真实 LLM 驱动**（需要可用的模型 provider）
- 动作执行器仍只支持「修改对象」一种规则；`rules` / `submission_criteria` 字段已落库但无规则编辑器
- 副作用的声明已落库，但**没有执行器**（通知 / Webhook / 触发调度均未实现）
- 函数仍是算术表达式求值，不是官方那种 TypeScript/Python 函数

---

### P3 — 治理（变更、历史、分支、提案、导入导出）

| 交付物 | 说明 |
|---|---|
| 工作副本 | 改动先入草稿，右上角 `保存` / `丢弃`；未保存数量角标（官方的 `1 edit`） |
| Review edits | 保存前弹审核面板，分 **Errors（阻塞）** 与 **Warnings（不阻塞）** |
| 破坏性变更确认 | 检测破坏性改动（删属性、改主键、改类型），要求输入实体名确认 |
| History / Restore | 全局与单资源历史；恢复后需再保存才生效 |
| Export / Import | 本体定义导出为 JSON、可导回（官方明确声明"不要依赖该 schema"，我们也标注为不稳定） |
| Usage | Reads / Writes / Interactions / Active users 四类读数 |
| Proposals | 非超管的改动走提案，由超管评审（替换现有"版本审批"） |
| Cleanup | 弃用 / 删除建议清单 |

**验收标准**
1. 任何改动在点保存前不落库
2. 有错误的改动无法保存；仅有警告的可以保存
3. 能查看并恢复历史版本
4. 导出的 JSON 能被导回并还原定义

**工作量**：全栈，约 6–8 天。**这是最大的一块，也是当前"点保存立即生效"体验的根本改变。**

#### ✅ P3 完成记录

**核心改变：从「点保存立即生效」改为「改动先入工作副本，点保存才落库」**

| 概念 | 实现 |
|---|---|
| 工作副本 | 新表 `ai_ont_wip`（按用户隔离），改动暂存于此 |
| 读取叠加 | `list_objects/properties/links/actions/functions`、`object_full` 支持 `owner_id` 参数，把草稿叠加到结果上——**界面上立刻可见，但库里没有** |
| 保存 / 丢弃 | 头部按钮 + 未保存数量角标（对齐官方的 `N edits`）；丢弃前二次确认 |
| 审核面板 | 保存前列出改动清单，分 **Errors（阻塞保存）/ Warnings（不阻塞）/ Destructive（需输入实体名确认）** |
| 导入 / 导出 | JSON 往返；导入默认入草稿，另有「直接导入（跳过审核）」并二次确认 |
| 用量 | 读数（Agent 工具调用）/ 写入（动作执行）/ 交互（定义改动），取自既有日志表，无额外埋点 |
| 清理 | 弃用/删除候选（无属性、无关系无动作无函数的孤岛、已 deprecated），可一键标记弃用 |
| 历史恢复 | 版本快照可恢复，**恢复也是一条草稿**，点保存才生效 |

**验收实测**

| 验收项 | 实测结果 |
|---|---|
| 1. 改动在保存前不落库 | 暂存改名后：接口返回的列表显示新名（`摄像机表_P3验证`），而 `SELECT name FROM ai_ont_object` 仍是 `摄像机表`；丢弃后列表回退 |
| 2. 有错误无法保存；仅警告可保存 | 缺显示名 → `ok=False`，列出 `对象类型「_p3_bad」缺少显示名`；仅缺描述/API 名（警告）→ `ok=True` |
| 3. 能查看并恢复历史版本 | 历史页显示 6 个版本快照，每个带「恢复」按钮；恢复走草稿 |
| 4. 导出的 JSON 能导回 | 导出 83 对象/1479 属性/33 关系/7 动作/10 函数；导回暂存 1612 项；丢弃后归零 |
| 附加：破坏性确认 | 删除操作在未输入实体名时 `ok=False` 并列出可输入的名称；输入正确名称后 `ok=True` |
| 附加：角标 | 暂存后角标 = 1，保存后消失 |
| 附加：清理/用量 | 清理 47 条建议；用量三个读数卡片正常渲染 |

**P3 期间发现并修复的 4 个缺陷（都不是本次新引入的）**
1. **部分更新被误判为破坏性变更**：草稿是局部更新（不带 `key_prop`）时，代码拿 `old.key_prop != d.key_prop` 判定"改了主键" → 误报。改为仅在草稿确实带了该字段时才比较
2. **删除草稿只带 code 时无法解析 id**：`remove_entity(kind, 0)` 直接报非法。新增 `_resolve_entity_id` 按 code 反查
3. **create 冲突在保存时才炸**：草稿是"新建"但库里已有同编码 → 应在审核阶段就报错。已补 object/action/function 三条 create 冲突检查
4. **软删除的行仍占着 `code` 唯一约束** → **删除过的编码永远无法重建**。`upsert_object` 改为：同编码（含已软删）存在时复活并覆盖，而不是报"已存在"

**已知未做的部分（如实标注）**
- **提案（Proposals）**：官方非超管的改动走提案、由超管评审。本项目沿用了既有的"版本发布待审批"机制（`version_pending` / `approve`），**但没有把普通定义改动接入提案流**——即非超管目前也能直接保存定义改动
- **用量缺「活跃用户数」**：需要按用户聚合调用日志，本版未做
- **破坏性确认只要求输入其中一个实体名**（多个破坏性改动时），官方是逐个确认
- 工作副本**没有过期/冲突处理**：两人同时改同一实体的定义不会互相提示
- `join_method` 等部分字段的中文名推导仍有边界情况

---

### P4 — 消费与图（实例层）

| 交付物 | 说明 |
|---|---|
| 实例层图（Vertex 风格） | 以真实对象为节点；`Search Around` 多步扩展；6 类布局；边方向与样式；保存视图；保存为图模板 |
| 对象探索（Object Explorer） | 实例搜索与过滤；**沿链接跳转（Pivot）**；结果集可视化（图表）；对结果集**批量执行动作** |
| 对象视图（Object Views） | 单对象页：属性面板 + 链接面板 + 可插入的动作 |
| Writeback | `Edits` 开关与可编辑属性 |
| 资产图谱归位 | 现有「图谱」（表/字段/指标/术语/概念）明确标注为**数据侧血缘**，与本体类型层图分开 |

**验收标准**
1. 能从一个对象沿链接跳转到关联对象
2. 能对筛选出的对象集批量执行动作
3. 实例图与类型层图在界面上清晰区分

**工作量**：全栈，约 8–10 天。

#### ✅ P4 完成记录

**核心新增：实例层（真实数据行）**——在此之前整个本体只有「类型层」的定义管理，看得到对象类型却看不到一台真实的摄像机。

| 交付物 | 实现 |
|---|---|
| 实例搜索 | `GET /ontology/instances/{code}`：在支撑表里按关键词/字段过滤真实行；只展示本体里声明且**真实存在**的列 |
| 对象视图 | 抽屉式单实例页：全部属性 + 关系跳转 + 可执行动作 + 写回表单 |
| **Pivot（沿关系跳转）** | `GET /ontology/instance/{code}/{key}/pivot`：**双向**遍历（关系是有方向的，从摄像机到告警记录要逆着走） |
| **实例图** | `POST /ontology/instance/graph`：以真实行为节点、关系为边，支持 1–3 步 Search Around，可按关系过滤 |
| **批量执行动作** | 选中多行 → 选动作 → 填参数 → 逐个执行（沿用白名单 + 审批门禁 + 审计） |
| Writeback | `POST /ontology/instance/writeback`：开启「可编辑」后可直接改属性值，仍然留痕 |
| 资产图谱归位 | 资产页的图谱标签改为「图谱（数据血缘）」，并加说明与本体类型层图区分 |
| 类型层图 | 已有（关系类型 → 可视化），本次在实例图上加了指向它的说明 |

**验收实测**

| 验收项 | 实测结果 |
|---|---|
| 1. 能沿关系跳转 | `沿「摄像机」找到 100 个告警记录表`（反向遍历）；正向（摄像机→分组）在同实例无外键值时如实返回"没有关联值" |
| 2. 能对结果集批量执行动作 | 勾选 50 个实例 → 动作选择器列出 2 个动作 → 参数表单带 `object_key` + `新名称`，显示"作用实例 50 个：1、2、3、4、5、6…" |
| 3. 实例图与类型层图清晰区分 | 实例图标题「实例层图（真实对象为节点）」+ 说明「节点是真实数据行…类型层图请看『关系类型 → 可视化』」；`graphDistinct=true` |
| 附加：对象视图 | 3 个分区（写回/关系跳转/可执行动作）、6 条关系、2 个动作、敏感字段带「敏感」标签 |
| 附加：Writeback 闭环 | 开启可编辑 → 改「安装位置」→ 提示「已写回 1 个属性并留痕」→ 重新打开已是新值 → **数据库确实变了**；审计仅 1 条（无重复执行） |
| 附加：实例图规模 | 摄像机 #1 扩展 1 步 → 21 个实例、20 条关系边 |

**P4 期间发现并修复的安全隐患（重要）**

`ai_ont_property.sensitive` 这一个标记**全部 1479 个属性都是 false**——从来没有被使用过。这意味着写回防护里"不写敏感字段"那一条**形同虚设**。实测把 `password` 写进真实表竟然成功了。

修复：
1. 写回增加**字段名启发式兜底**：`password/passwd/pwd/secret/token/api_key/private_key/credential/salt/signature/access_key/session_id` 一律拒绝写，无论本体里有没有勾 sensitive
2. 对象视图里这类字段也按敏感处理（值显示为 `••••••`，不进入可编辑表单）
3. 「业务语义回填」现在会自动把这些属性标记为 `sensitive`

**说明：一次数据损坏与还原**

验证写回时我用 `password` 字段做了尝试，**真的把摄像机 #1 的密码改成了 `x`**。该列原本为空（同类摄像机 2–5 全空），已还原为空值。无法 100% 确认原值，如实记录。

**已知未做的部分（如实标注）**
- **实例图不支持保存视图/图模板**（官方 Vertex 可以存成模板复用）
- 实例图节点上限 150、每步每关系最多 20 个邻居，超出会截断并在提示里说明
- **对象视图没有做成独立的可分享页面**（当前是探索器里的抽屉）
- 批量动作是**逐个串行**执行，没有事务语义（部分成功是可能的），失败项会列出前两条
- 实例层的写回只改真实列，**不写入本体变更留痕的对象级快照**（只有 `ai_action_log` + `ai_ont_change_log` 各一条）
- 6 类布局只用了 GraphCanvas 已有的几种，没有为实例图单独调优

---

### P5 — 高级类型系统（让概念真正完备）

| 交付物 | 说明 |
|---|---|
| Object type groups | 跨对象类型的分组，支持筛选 |
| Shared properties | 定义一次、多类型引用；只共享元数据不共享数据 |
| Value types | space 内的语义包装（邮箱/URL/UUID/枚举）+ 约束 + 版本 + 权限 |
| Struct | 结构体属性：含若干 field，由单个 struct 列支撑 |
| Interfaces | 接口定义、对象类型实现、接口层面的 link type 与 action type 约束 |
| Derived properties | 派生属性：源类型 = 关联对象，经 link 链（≤3 层）+ 聚合（9 种）+ collection limit（默认 10，最大 100） |

**验收标准**
1. 每种类型都有完整的定义、编辑、删除、引用检查
2. 接口可被多个对象类型实现，且约束在实现侧强制
3. 派生属性不能依赖另一个派生属性（官方限制）

**工作量**：全栈，约 10–14 天。**建议按实际业务需要裁剪**（见 §9）。

#### ✅ P5 完成记录

**已交付（六件事全部落地）**

| 交付物 | 实现 | 关键约束 |
|---|---|---|
| **对象类型组** | `ai_ont_group` + `ai_ont_group_member`，**多对多**（不同于「所属本体」的一对一） | 删除时做引用检查 |
| **值类型** | `ai_ont_value_type`：基础类型 + 语义约束（pattern/min/max/min_length/max_length/options）+ **版本** + 权限角色 | 改定义自动 `version+1`；有引用时拒绝删除 |
| **共享属性** | `ai_ont_shared_property` + 属性上的 `shared_code` | **只同步元数据**（类型/base type/值类型）到引用方；有引用时拒绝删除 |
| **Struct** | 属性上的 `struct_fields` JSONB | 由单个 struct 列支撑，界面可描述字段组成 |
| **接口** | `ai_ont_interface` + `ai_ont_interface_impl`，声明必需属性/关系/动作 | **约束在实现侧强制**：不满足的对象类型会被拒绝并列出缺项 |
| **派生属性** | 属性 `type_class='derived'` + `derived` 配置（源对象 / 关系链 / 聚合 / limit） | 关系链 **≤3 层**、limit **默认 10 最大 100**、**不能依赖另一个派生属性** |

**派生属性可实际计算**：沿关系链遍历真实数据（复用 P4 的实例层 Pivot）再按 9 种聚合汇总，界面上可「试算」。

**验收实测**

| 验收项 | 实测结果 |
|---|---|
| 1. 每种类型都有完整定义/编辑/删除/**引用检查** | 组：2 成员、引用检查返回 2；值类型：有引用时删除被拒（`仍有 3 处引用`）；共享属性：2 处引用时删除被拒；接口：有实现者时删除被拒；解除引用后均可删除 |
| 2. 接口可被多个对象类型实现，**约束在实现侧强制** | `video_cameras` 满足 → 通过；`video_alarm_records` 不满足 → **`被拒：告警记录表（动作：修改摄像机名称）`**，只有合规者被写入 |
| 3. **派生属性不能依赖另一个派生属性** | 校验返回 `派生属性不能依赖另一个派生属性（_p5_d2 本身是派生属性）`；界面同步给出该限制提示 |
| 附加：值类型约束 | 邮箱 pattern：`a@b.com` 通过、`not-an-email` 拒绝、超长同时报长度与模式两条 |
| 附加：派生边界 | 4 层关系链被拒、`limit=500` 被拒、非法聚合被拒并列出可用取值 |
| 附加：派生计算 | 摄像机 #1 的告警条数 = 10（limit 上限内匹配 10 条，1 层） |

**新增的表与列**
- 表：`ai_ont_group` / `ai_ont_group_member` / `ai_ont_value_type` / `ai_ont_shared_property` / `ai_ont_interface` / `ai_ont_interface_impl`
- 列：`ai_ont_property` 增加 `shared_code` / `derived` / `struct_fields` / `value_type_code`（属性字段数 22 → **26**）
- 新类型也接入了**工作副本**（`group` / `value_type` / `shared_property` / `interface`），删除路径走各自的引用检查，不能被绕过

**已知未做的部分（如实标注）**
- **接口的 link type / action type 约束只校验"存在同名项"**，没有校验关系另一端的接口类型是否匹配（官方可声明"目标必须实现某接口"）
- 值类型的 `roles`（权限）**只存不用**：界面上能填，但实例层读写没有按角色过滤
- Struct 的 `struct_fields` **只存不用**：不参与实例层读写（真实列仍按单列处理）
- 派生属性不支持 `collect_list`/`collect_set` 的**分页游标**，只按 limit 截断
- 对象类型组的**筛选**只做到列表展示与引用检查，没有接入对象类型列表的过滤器
- 派生属性计算是**实时遍历**，没有物化缓存（大数据量下会慢）

---

## 7.5 各阶段完成情况总览

| 阶段 | 状态 | 核心产出 |
|---|---|---|
| **P0** | ✅ 完成 | 左侧树状导航（资源列表 ⊃ Properties）、资源选中后切换为官方 9 页、Overview 按官方 7 分区排序 |
| **P1** | ✅ 完成 | 对象/属性/关系/动作的完整元数据（26/22/16/17 字段）、官方枚举、自动推导与回填 |
| **P2** | ✅ 完成 | 修通 `capabilities` 断链；`tool_description` 驱动工具描述、参数声明驱动工具 schema、调用前预校验、能力清单过滤、依赖可追溯 |
| **P3** | ✅ 完成 | 工作副本（改动先入草稿、Save/Discard、角标）、审核面板（错误阻塞/警告放行/破坏性确认）、导入导出、历史恢复、用量、清理 |
| **P4** | ✅ 完成 | 实例层：实例搜索、对象视图、双向 Pivot、实例图、批量执行动作、Writeback；资产图谱归位为数据血缘 |
| **P5** | ✅ 完成 | 对象类型组、值类型、共享属性、Struct、接口（约束在实现侧强制）、派生属性（≤3 层、9 种聚合、不能依赖派生） |

**跨阶段修复的真实缺陷（都不是计划内的）**

> **收口成果**：上表 22 条 + 收口时新增的 23 号，全部在
> `backend/tests/test_ontology_regressions.py` 有**对应回归测试**（23 项，编号一致），
> 任何改动都无法把它们悄悄放回来。收口还顺带修掉了**测试基建自身的漂移**：
> 测试 DDL 曾与 service 建表语句漂移 7 张表（`ai_ont_object` 少 `updated_time` 等），
> 现已抽成单一来源 `tests/_ont_ddl.py` 并加了防漂移断言。

| # | 缺陷 | 影响 |
|---|---|---|
| 1 | `ai_ont_*` 九张表在代码里**没有任何建表语句**（只存在于开发机数据库） | 全新部署直接失败 |
| 2 | `ai_agents.capabilities` **只在库里有列**，模型与接口 schema 都没声明 | 「本体接 Agent」整条链在第一步就是断的：前端勾了存不进、运行时读不到 |
| 3 | `ai_ont_action` **根本没有 `visibility` 列**，且 `upsert_action` 从不写它、`_ACT_COLS` 也不读它 | 动作的隐藏过滤**完全失效** |
| 4 | **软删除的行仍占着 `code` 唯一约束** | 删除过的对象类型编码**永远无法重建** |
| 5 | `ai_ont_property.sensitive` **1479 个属性全是 false**（该标记从未被使用） | Writeback 的"不写敏感字段"防护**形同虚设**，实测能直接写 `password` |
| 6 | 工作副本把**局部更新误判为破坏性变更**（草稿没带 `key_prop` 却拿它比较） | 普通编辑被要求输入实体名确认 |
| 7 | 删除草稿**只带 code 时解析不出 id** | 删除操作报"非法请求" |

### 7.5.1 差距清单驱动的工作（另一套编号，按 `ontology-gap-analysis.md` 的优先级）

> 上面 P0–P5 是**本计划自己的分期**。做完之后又按官方文档全量对账（361 页），
> 产出了另一份优先级清单（`ontology-gap-analysis.md` 的 P0–P9）。已完成的：

| 项 | 内容 | 状态 |
|---|---|---|
| **差距-P0** | 让 4 处「能填不生效」的字段真正执行：`submission_criteria` / `rules` / `side_effects` / 值类型 `roles` | ✅ 2026-10 |
| **差距-P1** | 值类型约束接到写入路径（动作参数） | ✅ 动作参数已接；实例层 Writeback 待接 |
| **差距-P2** | 函数能力升级：四种形态 + 类型化入参/出参 + 对象上下文 + 内置函数 + 运行/校验 | ✅ 2026-10 |
| **差距-P3** | 决策数据 + 决策谱系：决策成为本体一等对象，影响自动捕获 | ✅ 2026-10 |
| **差距-P4** | 对象权限：两层授权 + 单元格级安全 + **Agent 工具按调用者门控** | ✅ 2026-10 |
| **差距-P5** | 场景：编辑叠加式沙箱 + 读叠加 + 单事务合并 + 多场景对比 + 按执行上下文治理 | ✅ 2026-10 |
| **A** | 对象视图：Standard/Configured + Full/Panel + tabs→widgets + 真实渲染 + 版本 | ✅ 2026-10 |
| **B** | 索引：真建库索引 + 状态机 + 建议 + 5 分钟自动重试 | ✅ 2026-10 |
| **C** | 分支/提案：自动生成提案 + 每资源一任务 + 按任务审查 + 合并 + 变更记录 | ✅ 2026-10 |
| **D** | 演示数据：19 项一键载入/清除（登记表 + 孤儿认领） | ✅ 2026-10 |

**差距-P0 的产出**

- 新增 `action_engine.py`（纯函数）：提交条件（三类模板 + 单值/多值算子 + 可嵌套 AND/OR/NOT + 每条件失败信息）、
  规则解析（含 5 种赋值来源）、副作用解析（通知/Webhook + `{{参数}}` 模板）
- 重写 `execute_ontology_action`：**七道闸**（提交条件 → 值类型 → 规则/白名单 → 审批门禁 → 执行规则 → 副作用 → 审计）
- `side_effects` 真执行：通知写 `sys_user_notification`；Webhook 真发 HTTP（可 before/after、可阻塞）
- 新增试运行接口 `POST /ontology/action/test-run`（评估但**不写库**）
- 前端「规则」页从**推导出来的假表**换成真编辑器 + 试运行面板

**差距-P2 的产出**

- 新增 `function_engine.py`（纯函数）：受控表达式求值 + 33 个白名单内置函数、四种形态调度、类型化入参准备与转换、定义校验
- `ai_ont_function` 新增 `kind` / `outputs` / `config` 三列
- 前端函数弹窗：形态切换、入参/出参/形态配置编辑、内置函数速查、运行与校验
- Agent 工具 schema 与运行时**对齐**（聚合/HTTP/模型形态自动追加 `object_key`）

**这一轮又抓出的真实缺陷（都不是计划内的）**

| # | 缺陷 | 影响 |
|---|---|---|
| 8 | 子组件暂存改动**不刷新父页面「未保存」角标**（暂存逻辑有两份） | 用户改了东西却看不到待保存提示 |
| 9 | 试运行读的是**已保存**的定义，看不到正在编辑的草稿 | 试运行测的不是当前配置，功能形同虚设 |
| 10 | 函数入参声明了 `type` 但**运行时不做类型转换** | 界面/Agent 传字符串进来，`8 / 10` 变成 `'8' / '10'` 直接 TypeError |
| 11 | 老函数没声明入参时，**运行弹窗一个输入框都没有** | 库里原有 10 个函数根本无法运行 |
| 12 | 函数**保存时完全不校验**，`AVG(amount)` 这种从来跑不通的表达式照存 | 用户以为功能存在（与缺陷 5 同类） |
| 13 | `model` 形态最初猜错了助手服务类名 | 模型调用直接抛 `AttributeError` |
| 14 | 决策依据里存**对象属性快照**，含 `datetime`/`Decimal` | `json.dumps` 抛 `TypeError`，决策根本存不进去 |
| 15 | 中文标题推不出 ASCII 编码，回退到**秒级时间戳** | 同一秒建两条决策就撞唯一约束 |
| 16 | 决策的对象类型与动作的目标类型**可以不一致** | 执行时前后快照取错对象，捕获到的"下游影响"是假的 |
| 17 | `run_ontology_tool` **收了 `user_id` 却完全没用** | Agent 是绕开数据权限的后门：可读任何对象、调用任何动作 |
| 18 | `upsert_property` 名为 upsert，没带 `id` 时却**无脑 INSERT** | 静默产生重复属性行；权限判定读到互相矛盾的 `roles` |
| 19 | 行级策略表达式**只做语法检查**不真跑 | `user.password` 这类语义错误保存成功、运行期才炸 |
| 20 | `/action/execute` 控制器**没把 principal 传下去** | P4 的权限在 **HTTP 路径上完全不生效**（当时只在 Python 直调里验过） |
| 21 | 场景 `expires_at` 是 TIMESTAMP 列却传了字符串 | TTL 写入直接抛错，场景**建不出来** |
| 22 | `record_edit` 在场景不可编辑时**抛异常**而非返回结果 | 穿透成 500，而不是可读的拒绝原因 |
| 23 | 敏感名启发式把 `tokenizer_model`（模型名）**误判为密钥** | 写回会拒绝写这个合法列；收口时补的回归测试撞出来的 |
| 24 | `_table_columns` 用 `information_schema`（Postgres/MySQL 专属） | SQLite 上**永远返回空** → "物化"判定恒假，实例层整体失效；被 `except: return set()` 藏住 |
| 25 | 实例层大量使用 `::text` / `ILIKE` / `pg_total_relation_size` | 全是 Postgres 专属；项目声称支持 SQLite/MySQL，实际跑不通 |
| 26 | `upsert_decision` 的成功返回**没有 `ok` 字段**（其它 upsert 都有） | 调用方按 `ok` 判断会误判为失败（演示数据就踩了这个） |
| 27 | 提案 `save_on_branch` 的 `after` 只存传入子集 | 合并时把未提及字段（icon/description/status）**重置为默认值** |
| 28 | 视图筛选器算子（`contains`）与实例层算子（`like`）**不是一套词表** | 配了筛选却落到默认 `eq` 分支，**静默筛不出任何东西** |
| 29 | `_render_chart` 直接拼 SQL、签名里**连 principal 都没有** | **聚合绕过行级策略**——本体自己的图表组件就能算出不该看的数 |
| 30 | 问数执行路径**完全不读本体行级策略**；本体表名按 `ont_{code}` 拼而支撑表常是原名 | **问数可绕过对象权限**；prompt 里的表名是错的，LLM 会照着写不存在的表 |
| 31 | `_nl2sql` 构造模型客户端**没注入网关请求头**（同文件另两处都用了 `build_headers`） | opencode 网关返回错误文本，被当成 SQL 校验 → 报「仅允许 SELECT 查询」，问数**一直跑不通**且看不出原因 |
| 32 | `_extract_sql` 没处理工具化 Agent 要求的 JSON 输出 | JSON 尾部 `"}` 残留 → sqlglot 解析不出 Select → 同样报「仅允许 SELECT 查询」 |
| 33 | 可查询白名单只拼 `ont_{code}`，支撑表常是原表名 | 报「表不在白名单内」，本体支撑的表**根本查不到** |
| 34 | `_get_runtime('query')` 把 `usage` 为空的「通用」模型也算命中 | 专门配的本地 chat 模型不参与，问数被顶到额度受限的外部网关 |
| 35 | 问数**前端页面被当作孤儿页面删除**（`c27de533`），菜单仍指向它 | 从界面点「智能问数」是 **404**（本轮已补回页面并恢复菜单） |
| 36 | 问数**直连读**本体表 9 处、无契约；自己另养一套重复语义 | 本体改表结构问数会悄悄坏掉；语义两份、`sensitive` 两套各标各的（交集 **0**） |
| 37 | 敏感扫描规则用子串匹配 `"token"` | `prompt_tokens`/`completion_tokens`（计数）被**误标为敏感** |
| 38 | 统一语义接口里对 **JSONB** 列写 `COALESCE(x,'')` | Postgres 报「COALESCE types jsonb and text cannot be matched」，对象/属性/概念列表**全部变空** |
| 39 | 问数工具化 Agent 挂了 15 个工具、每题触发 **7.25 次**工具调用 | 每次都是一轮 LLM 往返 → 单题 ~10s；而工具给的信息**本地检索已全覆盖** |
| 40 | 本体语义块**全量倾倒**（85 个对象 / 1501 属性） | 实测 **37517 字符**，LLM 前缀计算大半花在无关对象上 |
| 41 | `semantic_context` 与 `object_table_map` 对**空 backing_table 的解析互相矛盾** | 一个回退成 `code`（指向不存在的表），一个按 `ont_{code}` → prompt 里写出不存在的表名 |
| 42 | 收尾阶段**重复检索**（同一问题检索两次）+ `ask()` 里指标/术语**重复加载** | 收尾白花 1802ms；慢路径多跑两次库查询 |
| 43 | 新加的计时日志用了 `%s` 风格 | 项目用 loguru（`{}` 风格）→ 打印出原始格式串，等于没打 |
| 44 | 基准集 `本体对象` 5 题指向**已软删**的 `orders`/`customers` 对象 | 该分类恒为 20%，量的是"不存在的东西"，掩盖真实能力 |

---

## 8. 与 Agent 接线的专项设计（重点）

这是本计划与"本体只是数据"这一痛点的直接对接。

### 8.1 现状

```
agent.capabilities → ont_codes → build_selected_ontology_tools(ont_codes)
                  → tool_schemas + grounding + sel_schemas
                  → 调度 run_selected_ontology_tool
工具命名：ont_fn__<code> / ont_action__<code>；list_ontology 常驻
```

### 8.2 目标

| 能力 | 做法 |
|---|---|
| 工具描述可控 | 动作/函数新增 `tool_description`，工具 schema 的 description 优先取它 |
| 参数由本体定义 | `parameters`（含对象引用、必填、默认值、枚举）直接生成 JSON Schema，不再手写 |
| 可查范围明确 | 对象类型的 `visibility` / `status` 决定是否暴露给 Agent；`deprecated` 默认不暴露 |
| 执行前可预检 | `rules` + 白名单在工具调用前校验，错误信息可读 |
| 依赖可追溯 | Dependents 反查，改本体前能看到"会影响哪些智能体" |
| 语义检索 | 对象类型的 `aliases` + 属性中文描述参与检索，提升自然语言命中率 |

### 8.3 验收（端到端）

对「问数助手」说一句业务话 → 命中本体动作 → 参数从工具 schema 注入 → 走白名单 + 审批门禁 → 写库 → 留审计 → 依赖与用量可见。

---

## 9. 明确不做的部分（诚实划定边界）

| 不做 | 理由 |
|---|---|
| 完整 Vertex（时序事件、媒体图层、场景模拟） | 超出当前业务需要；实例图只做"对象+链接"核心 |
| 完整 Quiver / Workshop / Slate 类消费端 | 我们已有自己的 Agent 与工作流体系，重复建设无收益 |
| Foundry Rules、Machinery、Map 集成 | 与本体建设目标无关 |
| TypeScript / Python 函数沙箱 | 我们是算术表达式求值器；引入代码沙箱是独立的大工程，且与"成熟第三方库优先"原则冲突。**若要函数具备真实计算能力，应改为声明式 SQL 聚合而非执行任意代码** |
| Marketplace / Gotham / Gaia 集成 | 平台特有 |
| 对象存储 v1/v2（Phonograph / Funnel）双轨、索引重建 | 我们是直连 PostgreSQL，无此架构层；`index_status` 用同步结果近似 |
| Branching 的完整 rebase / conflict 机制 | 只做"草稿 + 提案"两态，不做多分支并行演进 |

---

## 10. 风险与取舍

| 风险 | 影响 | 应对 |
|---|---|---|
| P0 是界面大改，用户需重新适应 | 中 | 保留"全部本体"视角；分区顺序严格照官方，降低学习成本 |
| P1 字段大量新增，回填质量不均 | 中 | 沿用"只覆盖自动生成值、不冲人工改动"的既有策略；无来源的字段留空并如实展示，不编造 |
| P3 工作副本是行为变更，可能打断现有用法 | **高** | 提供"直接保存"开关；迁移期默认开启草稿但允许一键关闭 |
| 官方文档自身有 7 处矛盾 | 中 | 已并列记录；实现时**取界面截图为准**（截图是实际产品行为） |
| P5 工程量最大且收益不确定 | **高** | 按需裁剪：`Shared properties` 与 `Value types` 优先（对多本体协作有直接价值），`Interfaces` / `Struct` / `Derived properties` 视业务再定 |
| 我们的 `ai_ont_function` 与官方函数模型语义差距大 | 中 | 文档中明确二者不同，避免对外宣称"对齐 Palantir 函数" |

---

## 11. 建议的起手式

**先做 P0。** 理由：

1. 它是**纯前端**改动，风险最低、见效最快
2. 它直接解决"三元素在界面上看不出来"这个原始问题——**包含关系画对了，概念自然就显形了**
3. 后续 P1–P5 全部建立在 P0 确立的信息架构上；先改架构能避免反复返工

P0 完成后可立即验收：左栏 `Properties` 缩进、对象类型 Overview 7 分区、属性 1 次点击可达。

---

## 附：证据索引

| 结论 | 出处 |
|---|---|
| 三元素官方定义、Dataset↔Ontology 类比 | `.research/palantir/raw/foundry__ontology__core-concepts.md` |
| 本体资源六件套 + Value type 定义 | `.../foundry__object-link-types__type-reference.md` |
| 对象类型 14 项元数据、必填清单、创建向导 9 步 | `docs/_palantir/notes/A-类型系统.md` §2 |
| 属性 13 项元数据 | 同上 §3 |
| 关系类型 11 项元数据、三种 join、基数四值 | 同上 §6 |
| 包含/依赖/引用关系图 | 同上 §11.1–11.3 |
| 左栏 `Properties` 缩进证据 | `docs/assets/palantir-ontology/02-oma-homepage-sidebar.png` |
| 对象类型 9 页 + Overview 7 分区 | `.../03-object-type-view-sidebar.png`、`.../04-object-type-overview-7-sections.png` |
| 关系类型 Join method 三选一 | `.../06-link-type-view.png` |
| 动作类型 9 页 + Input→Rules + Tool description | `.../07-action-type-view.png` |
| 8 条反模式 | `docs/_palantir/notes/B-应用与治理.md` §6.3 |
| 治理机制（save/restore/branch/proposal/export/usage/cleanup） | 同上 §4 |
| 官方 7 处自相矛盾 | `docs/_palantir-ontology-research.md` §0.3、§6.9 |
