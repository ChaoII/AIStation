# B — 本体的应用形态与治理

> 资料来源：`D:\AIStation\docs\_palantir\clean\` 下 38 个干净正文 txt（仅本地只读，未联网）。
> 本文只做事实梳理：所有内容均可在所列文件中找到依据；文档未写明的部分集中在第 7 节。
> 技术名词保留英文原词，解释性文字为中文。

---

## 1. 本体是什么

### 1.1 官方定位

- **运营层（operational layer）**：Palantir Ontology 是「组织的运营层」。它坐落在已集成进 Palantir 平台的数字资产（datasets、virtual tables、models）**之上**，把这些资产与现实世界的对应物连接起来——从物理资产（工厂、设备、产品）到概念（客户订单、金融交易）。
- **数字孪生（digital twin）**：在许多场景中，Ontology 充当组织的数字孪生，同时包含两类要素：
  - **语义要素（semantic elements）**：objects、properties、links；
  - **动能要素（kinetic elements）**：actions、functions、dynamic security。
- **不是数据目录、也不是 schema 设计工具**：定义组织的语义，是通过把既有数据源映射为 Ontology 中的 objects、properties、links 来完成的。文档明确说这「远不止数据编目（data cataloging）或 schema 设计解决方案」，而是为终端用户工作流定义稳固基础，包含所有字段的丰富元数据，以及对所有改动的细粒度安全与治理。
- **另一种定义**（core-concepts）：Ontology 是对世界的一种分类（a categorization of the world）。在 Foundry 中，Ontology 是组织的数字孪生，把组织的数字资产（datasets 与 models）整合为一个连贯整体；它通过把 datasets 与 models 映射为 object types、properties、link types、action types，形成组织世界的完整图景。

### 1.2 价值主张

- **投资 Ontology 的目标**：让组织能够**大规模地做出更好的决策**（facilitate better decision-making in an organization at scale）。
- **落地方式**：Ontology 深度集成进 Palantir 面向用户的分析与运营工具——用户可以用 Object Views 创建可复用视图、在 Object Explorer 中搜索对象、在 Quiver 中做复杂分析、在 Workshop 中构建高质量应用等。
- **动能部分的价值**（action-types overview）：Ontology 不是抽象数据模型，而是把每个本体概念映射到组织真实数据，使数据资产能驱动现实应用；数据资产随着用户决策与洞察被捕获为 Ontology 编辑而变得更丰富、更有价值。
- **让模型进入 Ontology 的价值**（ontology models 页）——三条：
  1. **可解释性（Interpretability）**：所有建模结果都以现实世界概念（对象类型的属性）表述，终端用户不需要懂机器学习，只需与 `forecast`、`estimate`、`classification` 这类简单概念打交道。
  2. **规模经济（Economies of scale）**：建模工作可以彼此叠加，而不是每个项目都为单一用例定制；一个用例产出的预测可立刻被后续用例复用。
  3. **规模化连接（Connectivity at scale）**：纳入 ML 模型后，Ontology 成为组织在**数据**与**逻辑**上的单一事实来源；模型编码了组织对未来的预期，Ontology 由此成为整个企业的数字孪生，从而支持在众多割裂建模工作下不可能做到的跨组织变化模拟。
- **把模型接入 Ontology 的端到端步骤**（原文顺序）：
  1. 在 Foundry 中创建模型（Create a model）；
  2. 配置 direct model deployment；
  3. 发布一个简单的 wrapper function，并可选地从另一个 function 调用它以编排更复杂逻辑；
  4. 在 Workshop、Vertex 及其他面向终端用户的应用中使用该 function 做实时推理。
  - 补充：Ontology 对象也可由利用模型做批量推理的 dataset 支撑。

### 1.3 与数据资产的关系：dataset ↔ ontology 类比（原样列表）

文档原文（core-concepts）给出的对照表：

| Datasets | Ontology |
| --- | --- |
| Dataset | Object type |
| Row | Object |
| Column | Property |
| Field | Property value |
| Join | Link type |

原文补充说明：可以把每个 object type 类比为一个 dataset；object 是 object type 的一个实例，正如 row 是 dataset 中的一条记录；dataset 的 column 类比 object 的 property，为某行提供附加信息；dataset 字段中的值（类似电子表格单元格）类比 object 的 property value；正如 datasets 能以多种方式 join，objects 之间也能基于属性值建立 links。

**关键概念定义（文档原文口径）**：

| 概念 | 定义 |
| --- | --- |
| Object type | 现实世界实体或事件的 schema 定义 |
| Object | object type 的单个实例，对应单个现实世界实体或事件 |
| Object set | 多个 object 实例的集合，代表一组现实世界实体或事件 |
| Property | 对象类型某一特征的 schema 定义 |
| Property value | 某 object 上该属性的值 |
| Shared property | 可在多个 object type 上复用的属性；用于跨对象类型的一致建模与属性元数据的集中管理 |
| Link type | 两个 object type 之间关系的 schema 定义 |
| Link | 两个 object 之间该关系的单个实例 |
| Action type | 「用户可一次性采取的一组对 objects、property values、links 的改动或编辑」的 schema 定义，还包括动作提交时发生的副作用行为 |
| Function | 接受输入参数并返回输出的代码逻辑；原生与 Ontology 集成，可接受 objects 与 object sets 作为输入、读取对象属性值、并被 action types 与建立在 Ontology 之上的应用使用 |
| Interface | 一种 Ontology 类型，描述某个 object type 的形状（shape）与其能力；提供 object type 多态，使共享同一形状的 object types 能被一致地建模与交互 |
| Object Views | 与某一对象相关的所有信息与工作流的中心枢纽，包括对象关键信息、链接对象、相关指标，以及与该对象相关的分析、看板与应用 |
| Roles | Ontology 的中心权限模型；与 Foundry 文件系统的 roles 类似，Ontology roles 授予对本体资源的访问权；可在 **Ontology 级别**或**单个资源级别**授予 |

### 1.4 Ontology 这个「产物」包含什么

`ontologies__ontologies-overview`：

- **一个 ontology 是存储本体资源（ontological resources / entities）的产物**，包含：Object types、Link types、Action types、Interfaces、Shared properties、Object type groups。这些统称 **Ontology resources**。
- Ontology 可以是**私有的**（分配给单个 organization）或**在多个 organization 间共享的**。共享 ontology 让不同组织的用户安全地共享数据与工作流；把实体分组到 ontology 中，确保只有指定组织的用户可访问这些本体实体。
- **与 space 的关系**：ontology 与 space 是 **1:1 映射**。新建 space 时，会同时创建一个同名 ontology，并带有与该 space 相同的 organization markings。私有 space 映射私有 ontology，共享 space 映射共享 ontology。
- **私有 vs 共享**对照：

| | 私有 ontology（Private ontology） | 共享 ontology（Shared ontology） |
| --- | --- | --- |
| 选择时机 | 需要这些对象的人都在同一个 organization 内 | 两个及以上 organization 的人需要同样的对象 |
| 应用的 organizations | 一个 | 两个或更多 |
| 可被授予访问权的人 | 该 organization 的 members 与 guest members | 任一被应用 organization 的 members 与 guest members |
| 随何创建 | 一个私有 space | 一个共享 space |

- 文档强调：**多个团队共用同一个 ontology 不构成创建第二个 ontology 的理由**；要控制哪些团队能触达哪些资源，应在持有资源的 projects 上给 groups 授予 roles。
- 注意：创建共享 ontology 本身**不会**让底层数据对所有被应用的 organization 可见。从私有项目引用进共享项目的 dataset 仍保留其来源 organization 的访问要求；在开发者移除继承来的要求之前，另一组织的用户仍被阻止查看该数据。

---

## 2. 产品分工

本节覆盖 4 个点名产品（Ontology Manager / Object Explorer / Vertex / Object Views），并附文档给出的更大应用集合对照。

### 2.1 Ontology Manager（OMA）

- **职责边界**：构建与维护组织的 Ontology。可用于广泛活动：从创建新 object type、定义新 action type，到把数据连接到 Ontology，以及排查数据是否在用户应用中更新。
- **访问方式（三种）**：
  1. 从 Workspace 侧边栏的 **Apps** 区选择 Ontology Manager 图标；
  2. 在 **Data Lineage** 中右键一个 object type，选择 **Configure object type**；
  3. 在 Foundry 首页 URL 后加 `/workspace/ontology`（例如 `https://example.website.com/workspace/ontology`）。
- **这个产品回答用户的什么问题**：**「组织现实世界的实体、关系与变更逻辑应该如何被定义、连上数据、并受控地发布给使用者？」**——即「怎么建、怎么改、谁能改、影响谁」。
- 别名：有时被称为 Ontology Management Application（**OMA**）。

### 2.2 Object Explorer

- **职责边界**：**搜索与分析工具**，用于回答关于 Ontology 层中任何事物的问题。用户可运行从简单关键词搜索到完整属性过滤的查询，全部在直观的点选界面中完成。
- 得到结果集后，可以：用 **exploration view** 探索、以**结果表**查看、选中具体对象查看其 **Object View**；**对比对象集**（compare and contrast object sets）；对对象集执行**批量 Actions**（如 writeback）；把对象集**打开到其它兼容应用**（如 Quiver）或**导出**；并**保存 Explorations** 以便随时回看最新结果。
- exploration view 是一组**预设且可配置的可视化**（如图表、地图），可进一步下钻到具体对象子集。
- 文档明确：Object Explorer **几乎无需预配置**（requires minimal configuration），面向**技术背景较弱的用户**（geared towards less technical users）。
- **这个产品回答用户的什么问题**：**「本体里有哪些对象符合我的条件？它们彼此如何关联？我能不能对这些结果做点什么、或把它们带去别处？」**

### 2.3 Vertex

- **职责边界**：可视化并量化（visualize and quantify）**跨组织数字孪生的因果关系（cause and effect）**。通过 Vertex 工具集，可以访问并探索组织已**整理并发布**的既有图，或构建新的 **system graphs**。
- 定位：对基于当前、预测或拟议条件的决策提供信息；提供工具集来**监控（monitor）、模拟（simulate）与优化（optimize）**运营决策，以最大化组织成果。
- 文档列出的四类帮助（原文四项概括）：
  - **Bring transparency**：通过探索跨越职能孤岛的整个网络的实时视图；
  - **Focus on what matters**：对主要风险与机会做集中告警，以及它们如何影响目标；
  - **Simulate the future**：把分析与运营结合，找出最有影响力的可做改动；
  - **Learn and optimize**：提升数据清晰度与模型准确度，看清什么在起作用并走向全局最优。
- 启动方式：从 Foundry workspace 侧边栏 **Apps** 区的 **Operational Applications** 分组下选择 Vertex，然后点 `+ New Graph`。
- **这个产品回答用户的什么问题**：**「在这个系统里，一个变化会沿什么路径影响什么？当前/预测/拟议条件下，网络长什么样、瓶颈在哪、动哪里最有效？」**

### 2.4 Object Views

- **职责边界**：**对象数据的可复用表示（reusable representations）**；是与某个对象相关的所有信息的中心枢纽，包括属性数据、对象链接与相关应用。
- **两类**：
  - **Standard Object Views（标准）**：标准化、开箱即用的表示，自动反映 object type 的配置；对所有 object types 都可用；无需任何配置即可提供一致的对象数据查看方式。
  - **Configured Object Views（已配置）**：用 **Workshop** 构建的完全可定制表示，可为特定工作流提供情境化体验。创建后成为默认视图，但用户始终可切回标准视图。标准与已配置视图作为**一等查看选项并存**：没有配置视图时默认显示标准视图，配置视图建好后标准视图仍可访问，用户可随时切换。
- **两种形态（form factors）**，标准与已配置都提供：
  - **Full Object Views**：全面的对象概览，深入展示所有相关信息；
  - **Panel Object Views**：用于集成进其它应用，应聚焦展示特定工作流最关键的数据。
  - 文档给的例子：`Patient` 对象的 full 配置视图可包含核心人口统计/生命体征/护理细节、链接的检查与处方与诊断、基于历史住院记录的分析趋势；同一个 `Patient` 的 panel 配置视图可能只显示人口统计与生命体征信息，以便在其它应用中快速提供该工作流最关键的访问。
- 从 `object-views__widgets-properties-links` 得到的补充事实：**Properties widget** 是任何新定义 object type 的**默认 Object View**（其页签作为默认视图创建）。
- **这个产品回答用户的什么问题**：**「关于这**一个**对象，我（或某个工作流）该看到什么、能跳到哪里、能对它做什么？」**

### 2.5 文档给出的「本体感知应用」全景与选型对照

`ontology__applications` 说明：Foundry 内有一批**原生在本体之上运行**的应用，共同构成支持多种用例与用户画像的分析与运营平台。文档给出每个应用的定位：

| 应用 | 文档定位 |
| --- | --- |
| Object Views | 与某个对象相关的所有信息与工作流的中心枢纽：关键「传记数据」、所有链接对象、关键相关指标，以及指向（或嵌入）相关分析、看板与应用 |
| Object Explorer | 对 Ontology 层中任何事物提问的搜索与分析工具；可视觉化组合从简单过滤到 Search Around 的查询；可用 exploration view 探索或用结果表查看；可对比对象集、对对象集批量执行 Actions（如 writeback）；可导出或打开到兼容应用（如 Workshop）；**无需预配置**，面向非技术用户 |
| Quiver | 在 Ontology 层做高级分析工作流：可视化点选界面 + 强大图表库；支持从简单线性下钻到高度分支的复杂分析（含聚合与统计函数）；原生支持时间序列分析；分析可模板化为只读看板 |
| Workshop | 在 Ontology 层上点选式无代码应用构建；比其它点选工具做的看板更动态、更交互；借助高质量 Layouts 与易用但精巧的 Events 系统，目标是与定制 React 应用一样友好、高质量 |
| Slate | 更灵活的应用构建器，但比 Workshop 需要更多技术配置与代码；可与 Ontology 层交互，也可**直接与 Foundry datasets 交互**；支持基于 Web 开发范式的显著视觉定制，功能面广，但构建与维护的技术门槛更高 |
| Carbon | 把 Foundry 中多个资源或应用组合成高度定制的 workspace；可组合分析结果（看板、Workshop/Slate 应用）与开箱能力（Object Views、Object Explorer），让工作流构建者完成「最后一公里」定制 |
| Map | 在地理空间情境中汇集并分析对象与其它数据 |

**应用对照表（原文表格，含 4 个维度）**：

| Foundry Application | Primary use case | Workflow Style | Configuration Model | Objects or Datasets |
| --- | --- | --- | --- | --- |
| Object Views | Discovery | Workflow-specific | Walk-up usable | Objects |
| Object Explorer | Discovery & Analysis | Exploratory | Walk-up usable | Objects |
| Quiver | Analysis & Dashboards | Exploratory（Analytical 模式）；workflow-specific（Dashboard 模式） | Walk-up usable（Analytical 模式）；customizable（Dashboard 模式） | Objects |
| Workshop | Applications & Dashboards | Workflow-specific | Customizable | Objects |
| Slate | Applications & Dashboards (complex) | Workflow-specific | Customizable | Objects（推荐）与 Datasets |
| Map | Geospatial | Exploratory 或 Workflow-specific | Walk-up usable | Objects |

**三个维度的定义（文档原文口径）**：

- **主要用例**：Discovery（发现）、Analysis（分析）、Dashboards（看板）、Applications（应用）。
  - Discovery：帮用户找到正确的信息或工作流；主要通过两个核心能力实现——**curated content hubs**（也称 landing pages 或「360 视图」）与 **search**（关键词自由文本搜索，以及通过链接遍历或下钻的更迭代表索）。
  - Analysis：回答从简单（某产品的平均客户留存是多少？）到非常复杂（三个人群在留存与整体营收上跨所有产品及单个产品如何比较？）的问题；分析路径是探索式的，由终端用户自己定义，通常高度迭代。
  - Dashboards：预配置可视化的集合，主要被更广的消费型用户以只读方式使用；常把有意义的 Analysis 转化为周期报表或运营监控；特点是有大量图表与可视化，但可定制性与交互性不如 Applications；常被参数化以便过滤到不同数据子集。
  - Applications：交互式定制运营界面，面向特定用户群解决特定问题；通常比看板更复杂，面向让用户遵循特定「在轨（on-rails）」工作流；除策展的分析内容外，通常还有若干工作流元素，并经常捕获用户输入（如 writeback）。
- **工作流风格**：**Exploratory**（无需 builder 预配置，数据建模进 Ontology 后即可开箱使用，路径由终端用户定义；主要是 Object Explorer 与 Quiver）与 **Workflow-specific**（需要 builder 用户预先配置；典型有两类用户群——配置的 builder 与下游终端用户；Workshop 与 Slate 模块都需要 Builder 在编辑模式中预配置）。文档指出 Quiver 同时容纳两种风格：主模式是探索式，但产出可配置为更广泛消费的 workflow-specific 产物（Quiver Analyses → Quiver Dashboards）。
- **配置模型**：**Walk-up usable**（几乎无需配置或维护负担即可立即有效使用；例如 Object Explorer 配置需求极少，Ontology 定义好后开箱即用）与 **Customizable**（需要前置投入，常由单独的 builder 用户实现界面；也意味着更高的持续维护成本；但产出通常是贴合特定工作流的专用界面；Workshop 与 Slate 属此类）。

### 2.6 产品之间如何衔接（文档可确认的衔接点）

- Ontology Manager 是**定义与发布的入口**：object type / link type / action type / function / interface 都在这里定义；改动必须 Save 后才对他人与用户应用生效。
- Object Views **可由 Ontology Manager 的属性配置影响**：Properties widget 的配置与 Ontology Manager 中「Edit Properties and Backing Dataset」紧密相关；每个属性在 OMA 有单独设置面板，决定它在 Object View 中的显示方式（prominent / normal / hidden、render hints 等）。属性可编辑性需要 OMA 侧两处设置（dataset 层启用 edits + 属性层挂 inline edit action）。
- Object Variables 的 Actions widget：在 Object View 中添加 **Actions** widget，可把某个 action type 的 RID 配成按钮（步骤见 action-types 入门：复制 action RID → 粘贴到 Action RID 字段 → 配置默认值把参数绑定到 Current object、显示选项设为 Hidden）。
- Object Explorer 可**打开到其它兼容应用**（如 Quiver、Workshop），也可把对象集导出。
- Vertex 图**可嵌入其它 Foundry 应用**，例如 Object View 或 Workshop（通过 **Vertex widget**）；图模板（graph template）支持这种嵌入。
- Vertex 与 OMA 的衔接：**Link Merge** 在 Ontology Manager 的 **Vertex Ontology Capabilities** 区配置，配置后对象可被自动分组进两个节点之间的边；边方向也可在 Ontology 层用 type classes 配置。
- Action log 与 Workshop 的衔接：可用 **Action Log Timeline** widget 在看板/模块中按时间线查看 action log 对象类型；action log 对象类型可在 Workshop 中 union 起来；也可与对象评论一起显示在 **Comments** widget 中。
- Carbon 可把 Object Views、Object Explorer 等开箱能力与 Workshop/Slate 应用、看板组合成定制 workspace。

---

## 3. Ontology Manager 的界面结构

`ontology-manager__overview` 把 OMA 界面拆为以下要素（文档原文列举）：Ontology Manager navigation、Discover view、Object type view、Property editor view、Link type view、Action type view、Function type view。

### 3.1 两个常驻元素：顶栏与侧边栏

- 文档明确：OMA 的**两个常驻元素**是 **top bar（顶栏）**与 **sidebar（侧边栏）**，二者作为导航元素。
- **顶栏的三个主要功能**：
  1. 搜索 Ontology 资源；
  2. 创建新的 Ontology 资源；
  3. 在分支之间导航，或创建新分支。
- **侧边栏**：提供到 OMA 内不同资源、页面或应用的便捷导航。

### 3.2 首页（home page）侧边栏条目

> 说明：文档没有一份「侧边栏条目总清单」。下列条目是从多个页面各自表述中提取的，原文标注了它们的归属。

| 条目 | 文档依据与说明 |
| --- | --- |
| **Discover** | 「Discover view」是一个高度可定制的落地页。默认展示 favorite object types、recently-viewed object types、favorite groups。若用户是 Ontology 新手，会呈现两个专门区块：一个显示该 Ontology 中最近修改过的所有 object types，一个显示所有 prominent object types。可配置页面出现哪些区块及每区显示条目数；可选区块包括 “Recently viewed object types”“Favorite object types”“Favorite groups”，还可为某个特定 group 单独加一个区块以浏览该组内所有 object types |
| **Object types** | 首页侧边栏可选页面；可按 visibility、development status、indexing issues 过滤。支撑数据源未注册、或未能重新索引到 Object Storage v1（Phonograph）的 object types，会在对象类型页的 issue 列显示红色错误信息 |
| **Link types** | 首页侧边栏可选页面；过滤维度同上 |
| **Action Types** | 首页侧边栏可选页面；过滤维度同上。（入门文档也写：在 Ontology Manager 中选左侧边栏的 **Action types**，再选右上角 **New action type**） |
| **Shared Properties** | 首页侧边栏可选页面；过滤维度同上 |
| **Interfaces** | 首页侧边栏可选页面；过滤维度同上 |
| **Functions** | 首页侧边栏可选页面；过滤维度同上 |
| **Unsaved changes** | 「从 homepage sidebar 选择 **Unsaved changes**，查看你做出的所有未保存改动的列表」 |
| **History** | 「选择 homepage sidebar 的 **History** 页签，查看所有已保存的 Ontology 改动列表，含改动时间与执行用户」。默认折叠，点下箭头展开某条改动看细节。在 **Ontology history** 页面还可选择隐藏你无权查看的对象/链接类型改动；可把同一作者的改动合并成单条显示 |
| **Proposals** | 「通过 side tab 导航到 **Proposals** 页」，可选择查看所有 ontology proposals。分组页签：My proposals、Assigned to me、In review、Merged proposals、Closed proposals |
| **Main branch updates** | 分支场景：当 main 有新改动时，侧边栏的 **Main branch updates** 页签上出现蓝色指示；进入该页可查看自上次 rebase（或分支创建）以来的传入改动 |
| **Advanced settings** | 「从应用首页选择 **Advanced settings** 页，然后选择 Export / Import」——导出与导入 Ontology 工作状态的入口 |
| **Cleanup** | Ontology cleanup 工具：「该视图可从工具的首页访问」；点 Start cleanup 后生成候选列表。cleanup 页含一个子页用于自定义 flags 及其优先级；保存改动返回 Cleanup 主标签页时会提示重新计算清理队列 |
| **（分支场景的）Conflicts / Errors / All changes** | rebase 过程中：有冲突则被重定向到 **Conflicts** 页签；只有错误则被重定向到 **Errors** 页签；rebase 期间 main 的改动加载到分支，本分支已保存改动被重新载回工作状态，可在 **All changes** 页签查看 |

### 3.3 打开某个资源后的通用导航行为

- **Back home**：打开 object type、link type 或 action type 后，可从视图侧边栏左上角选择 **Back home**。**悬停** Back home 按钮会弹出快捷链接：最近编辑过的 object types、link types、action types，以及与当前查看资源相关的所有资源。
- **搜索**：header 中间的 Search 栏，点击或按 `Cmd/Ctrl + K` 打开搜索对话框。可搜索任何 object type、property、link type、action type、shared properties、interfaces 或 functions。搜索结果会高亮匹配到的字段；可用上下箭头在结果间移动并查看预览；选择 Open 或回车打开选中项。在首页使用搜索栏会更新首页为匹配的资源列表。
- 资源视图左下角有一个 **footer**，显示该资源最后被编辑的时间与用户。

### 3.4 视图一：Object type view（重点）

**结构**：选择一个 object type 会打开 object type view，包含两部分——**左侧带页面选择的 sidebar**，以及**右侧被选中的页面（selected page）**。

**Object type 的 Overview 页含以下分区**（文档按图中编号列出，**仅给出名称**）：

1. Object type metadata（对象类型元数据）
2. Properties（属性）
3. Action types（动作类型）
4. Link type graph（链接类型图）
5. Dependents（依赖项）
6. Data（数据）
7. Usage（用法）

**发生在该页面上的跳转**：

- 从 Overview 页的 **Properties** 区选择一个 property → 打开 **property editor view**（属性编辑器视图）。
- 从 Overview 页的 **link type graph** 选择某个 link type → 打开 **link type view**。
- 从 Overview 页的 **action type 区**选择某个 action type → 打开 **action type view**。
- 从 Overview 页的 **function type 区**选择某个 function type → 打开 **function type view**。
- 在 **Overview 页签**还有 usage 图（30 天高层使用摘要，帮助快速理解对资源做破坏性改动的影响）。

**其它被文档提及的 object type 相关页签**：

| 页签/区域 | 文档依据 |
| --- | --- |
| **Usage**（专门页签） | 详细使用指标：过去 30 天内谁使用了每个 object type、何时、在哪些 Foundry 应用中；也可从 Overview 页 usage 图的 **See more** 进入 |
| **History** | 审阅单个资源的改动：资源页的 History 页签列出该资源的编辑（含你的未保存改动、以及所有已保存改动及其时间与用户） |
| **Dependents** | 作为 Overview 页分区列出（名称，无进一步描述） |
| **Data** | 作为 Overview 页分区列出（名称，无进一步描述） |
| **Security** | 资源保护场景：「也可在 **Security** 页签下审阅适用的 policy」 |
| **Datasources** | action log 场景：「打开该 object type，选择 **Datasources** 页签，然后在 **Edits** 区启用 *Only allow Action types with action logs*」；该开关在对象类型已启用 edits 时才出现（先在 Datasources 页启用 **Allow edits** 并保存，再回来） |
| **Capabilities** | Vertex link merging：「在 Ontology Manager 的 Vertex Ontology Capabilities 区配置 **Link Merge**」；action log：「打开该 action type，选择 **Capabilities** 页签，找到 **Create action log objects** 区」。注意：Capabilities 未出现在 overview 页列出的 view 清单里 |

**资源保护状态在 object type 上的可见性**（branching）：保护状态在 Ontology Manager 的 **Overview** 页签可见。

### 3.5 视图二：Property editor view

- 从 object type 的 Overview 页 **Properties** 区选择任一 property 即打开属性编辑器视图。
- 文档未逐条罗列该视图内的分区（见第 7 节）。

### 3.6 视图三：Link type view

- 从 object type Overview 页的 link type graph 选择 link type 即打开。
- **页签**：**Overview** 与 **Datasources**（文档明确「with Overview and Datasources pages」）。

### 3.7 视图四：Action type view

- 从 object type Overview 页的 action type 区选择即打开。
- **页签**：**Overview**、**Logic**、**Observability**。
- **Observability** 页签：显示该 action 在**过去 30 天**的近实时使用情况，以及为该 action 定义的**监控规则（monitoring rules）**及其状态。
- 其它被文档提及的 action type 页签/区域：
  - **Parameters** 页签：「选择 **Parameters** 页签获取参数总览」（入门示例中 Ticket 与 Priority 参数已根据 Rule 自动创建）；
  - **Rules** 页签：「在 Overview 页签加 Description，或在 **Rules** 页签加要修改的额外属性」；
  - **Security & Submission Criteria** 页签：提交条件（submission criteria）在其 **Execution** 区的 **Condition** 中创建；
  - **Capabilities** 页签：action log 的 **Create action log objects** 区（界面描述为 *Generate an object every time this action is triggered successfully*），其下含 **Summary** 区与 **Values to log** 区（分 **Required values** 与 **Optional values**）。

### 3.8 视图五：Function type view

- 从 object type Overview 页的 function type 区选择即打开。
- **页签**：**Overview**、**Configuration**、**Observability**。
- **Usage History 面板**：记录哪些应用使用过该 function 的任意版本，以及各自的版本信息；可从该面板导航到这些应用以升级 function 版本。
- **查看历史版本**：默认显示最新版本；用左侧面板的版本下拉选择器查看其它版本。
- **导航到 Functions Code Repository**：对 function 的修改只能在 Functions Code Repository 中进行；用实体视图右上角的 **Open in Code Repository** 按钮导航过去。
- **Observability** 页签：显示该 function 过去 30 天的近实时使用情况，以及为其定义的监控规则及状态。

### 3.9 搜索与过滤（navigation 页）

- 搜索对象范围：object type、property、link type、action type、shared properties、interfaces、functions。
- 首页六个列表页（Object types / Link types / Action Types / Shared Properties / Interfaces / Functions）支持按 **visibility**、**development status**、**indexing issues** 过滤。
- 索引问题提示：支撑数据源未注册、或未能重新索引进 Object Storage v1（Phonograph）的 object types，会在对象类型页的 issue 列显示红色错误信息。

---

## 4. 变更与治理机制

### 4.1 Save changes（保存改动）

**解决什么问题**：在 OMA 中的任何改动都先**本地存于 work-in-progress（工作状态）**；改动要对他人可见、并反映到面向用户的应用中，**必须保存**。

**流程**：
1. 在应用右上角的 Application header 选择 **Save**；
2. 打开 **Review edits** 对话框，审阅所有改动；
3. 最后选择 **Save** 更新 Ontology。

**错误与警告**：
- **Save 按钮灰显**可能是存在阻止保存的**错误**。解决方式：滚动改动查看行内错误信息，或在 **Review edits** 对话框顶部选择 **Errors** 页签查看。
- Review edits 也会**行内**与在 **Warnings** 页签显示**警告**（鼓励做的改动）；**错误必须处理才能保存，警告不阻止保存**。
- 遇到错误时，可用 open shortcut 在保存前导航到需要编辑的资源。
- **Functions 的改动只能在 Functions 仓库中做，不能在 Ontology Manager 中做**；可从 OMA 的 Functions Entity view 导航到 Functions Repository。

**更新与合并冲突**：
- 若在你开始改动之后 Ontology **已被他人保存**，Save 也可能灰显。此时需在 Review edits 对话框顶部选择 **Update**，把他人的改动与自己的合并。
- 可能与他人改动存在 **merge conflicts**，会被提示解决；可选择**保留 Ontology 最新版本中的改动**，或**用自己工作状态中的改动覆盖**。

**丢弃改动**：
- 你在 Ontology 中编辑的**每个资源**在 Review edits 对话框中各有自己的条目；悬停该条目并选择垃圾桶图标即可丢弃对该资源的改动。
- 任何时候都可丢弃全部未保存改动：选择应用右上角 header 的 **Discard**，或 Review edits 对话框底部的 **Discard**。

**回应警告消息**：
- 审阅改动时可能收到要求确认后才能保存的警告。
- 文档明确原因：**对 object types 及其属性的编辑可能对依赖这些对象类型的应用造成破坏性影响（application-breaking impact）**；此外，**若对象类型启用了 writeback，编辑它时要格外小心，确保该类型对象的编辑历史不会被移除**。
- 确认流程：阅读警告中所述改动影响并理解含义后，**输入你所编辑实体的名称**才能继续保存。
- 完整的「哪些改动可能是破坏性的」清单在 **potential breaking changes** 文档中（不在本次文件内，见第 7 节）。

**保存失败排查**：
- 后端服务在保存时出错会给出 **error toast（弹出提示）**；在解释为何无法保存的文本末尾会打印错误名，错误名前缀为 **`OntologyMetadata:`** 或 **`Phonograph2:`**。
- 文档建议：看到错误信息时在文档中搜索该错误名，看是否有记载与补救方式。

### 4.2 Restore changes（审阅与恢复改动）

**解决什么问题**：全局或单资源地审阅改动历史，并把某个 object type 恢复到较早版本。

**全局审阅**：
- **未保存改动**：从 homepage sidebar 选择 **Unsaved changes**，查看你做出的所有未保存改动列表。
- **已保存改动**：选择 homepage sidebar 的 **History** 页签，查看所有已保存 Ontology 改动列表，含改动时间与执行用户。默认折叠，点某条改动上的下箭头可展开细节。

**全局过滤**：
- 在 **Ontology history** 页面，可以选择**隐藏你无权查看的对象与链接类型的改动**。若未启用该选项，你能看到「发生过改动」，但看不到更多细节。
- 改动历史中**每条记录对应用户的一次保存**。
- 可选择**把同一作者做出的改动合并成单条**以精简视图。

**单资源审阅**：
- 在 Ontology 资源页面选择 **History** 页签，显示该资源的编辑列表，包含：你对该资源的未保存改动；所有已保存改动（含时间与执行用户）。
- 资源视图左下角的 **footer** 显示该资源最后被编辑的时间与用户。

**恢复单个 object type**：
1. 选择 **restore 按钮**（逆时针箭头图标）；
2. 选择 **Confirm**。
- **关键约束**：把 object type 恢复到较早版本后，**你所选条目之后做出的任何改动都会被撤销**；这些改动会被加入你的**工作状态**，因此**必须保存改动**，恢复才会生效。

### 4.3 Branching（分支）

**解决什么问题**：Ontology 与 **Global Branching** 集成，以支持对本体资源进行**安全、隔离的开发**。文档覆盖在分支上增改资源、rebase 与冲突解决、审阅与合并流程，以及已知限制。

**术语**：
- **Ontology proposal**：当你在**包含 ontology 改动的分支**上创建 Global Branching proposal 时，会**自动创建**一个 ontology proposal，用于跟踪本体特有的改动。ontology proposal 包含 reviews、名称，以及"正在合并进 main 的 ontology 改动"的描述等元数据。

**角色/权限相关状态**：
- 资源可在父项目的 **Files** 页签查看与管理其**保护状态（protection status）**。
- 资源**必须先迁移到 project permissions** 才能被保护。
- 一旦启用保护，就必须在单独分支上改动并创建 proposal 才能合并进 main 分支。
- 保护状态在 OMA 的 **Overview** 页签可见；适用的 **policy** 在 **Security** 页签可审阅。
- 修改受保护资源时，**Save 对话框被替换为 Create and save to branch**，要求你把改动保存到新分支。

**在分支上增改资源的流程**：
- 在 OMA 中新建分支，或用分支选择器进入已有分支。
- 新建分支：打开分支选择器 → **Create new branch** → 在对话框中填标题与描述。
- 若你已有想纳入分支的 ontology 改动，可在 save 对话框中选择 **Save to new branch** 创建独立分支承载这些改动。
- **若你修改了任何受保护的 ontology 资源，会被强制保存到新分支。**
- **只能从 main ontology（即 `main` 分支）分支。**
- 在分支上时，界面底部的 **branch taskbar** 会显示当前分支名与附加元数据。

**资源保护支持范围**：

| 支持保护 | 不支持保护 |
| --- | --- |
| Object types | Type groups |
| Action types | Rule sets（修改 rule set 时，按其所含 object type 的保护状态执行） |
| Link types | |
| Interface types | |
| Shared property types | |

**Rebasing 与冲突解决**：
- 背景：你在分支上引入改动的同时，`main` 也可能收到他人的新改动。**Rebasing 把 main 的最新改动并入当前分支**。
- **自动 rebase**：若你的 global branch **不含** ontology 改动，rebase 自动发生。**一旦你在分支上引入 ontology 改动（包括对某个 object type 建立索引），就需要手动 rebase**。
- 提示：当 main 有新改动时，侧边栏 **Main branch updates** 页签出现蓝色指示。
- 操作：进入 **Main branch updates** 页查看自上次 rebase（首次手动 rebase 则是自分支创建）以来的传入改动 → 选择 **Rebase branch**。
- 无冲突或无错误 → rebase 自动完成，分支为最新。
- 有冲突 → rebase 保持「进行中」，你被重定向到 **Conflicts** 页签解决；若**只有错误**，则重定向到 **Errors** 页签。
- rebase 期间的状态：**main 的改动被加载到你的分支，而你分支上此前已保存的改动被重新载回工作状态**，可在 **All changes** 页签查看。此状态让你能同时看到并访问来自 main 与分支的改动。当某本体资源在两个分支上都有改动时，**默认显示你的分支版本**。
- 冲突解决方式（逐资源）：**Use Main branch changes** 或 **Keep current branch changes**；也可以直接导航到该资源应用 **custom changes** 来解决冲突。文档例子：`Palantir employee` object type 在 main 与分支上都改了 display name，选择保留哪一版；也可做自定义改动（把 display name 从 "Palantir employee" 改成 "Current employee"）从而使冲突因该自定义改动而解决。
- 解决所有冲突后，还需在处理完所有错误前完成 rebase。
- 结束：选择 **Finish rebase and save**，分支即为最新；可继续在分支上工作并定期 rebase。

**合并要求（准备送审）**：
- 准备就绪后，在 branch taskbar 选择 **Create proposal** 图标创建 proposal，填名称与描述。
- 创建 proposal 时会运行 **merge checks**，验证 global branch 上的资源能否合并进 `main`；检查失败可能包括分支与 main 的冲突，需先 rebase。
- **请求评审**：可通过 branch taskbar、Global Branching proposal 页或 ontology proposal 页添加评审人。在 ontology proposal 页进入 **Review changes**，选择 **Invite reviewers**。对已迁移到 projects 的 ontology 资源，选择 **View policies** 查看基于相关项目策略哪些评审人是必需的。
- **每个 ontology 资源被视为一个独立 task**。资源名旁的状态标签表示整体审批状态；右侧的 **Your review** 区用于提交评审。
- **重要细节**：在 Global Branching 中 ontology 实体被当作各自独立的资源，但它们被归入**单个本地 ontology proposal**。因此**给一个 ontology 资源加评审人，实际上等于把该评审人加到所有 ontology 资源**。
- 可在 proposal 中各个 task 上留下评论以提供改动背景；通过最右侧的 **Comments** 侧边栏进入 task 的 Comments 区。

**评审 proposal**：
- 在 **Review changes** 页签，评审人可 approve 或 reject 单个 task。
- **无权限的用户仍可评审**（例如表达意见），但这不会影响 task 的批准状态。
- **具有审批权限的用户即使未被加为评审人也可以批准 proposal**。文档明确：**评审人列表用于跟踪谁应该评审，而不是用来限制批准**。
- 在 ontology proposal 中，评审人可以查看 proposal 细节，并批准或拒绝**所有已修改资源**或**特定 ontology 资源**的改动。
- 一旦满足 policy 要求，已批准资源的状态从 **In Progress** 变为 **Approved**；此后若其它检查都通过，就可以合并 proposal。

**合并分支**：
- 准备把改动合并进 main 时，必须**合并 Global Branching proposal**；这会**自动启动 ontology 的合并流程**。
- 操作：选择 branch taskbar 中的合并图标，或在 Global Branching 中进入 proposal 页选择 **Merge proposal**。

**已知限制（原文五条）**：

| 限制 | 说明 |
| --- | --- |
| **Datasource deletion** | 当冲突发生在某个 object type 上、且其 backing datasource 在 `main` 上被替换或移除时，**选择保留你的分支改动会导致合并失败**；此时应选择 main 分支改动 |
| **Conditional formatting deletion** | 当冲突发生在某个 property type 上、且条件格式规则集在 `main` 上被替换或移除时，**选择保留你的分支改动会导致合并失败**；此时应选择 main 分支改动 |
| **Pipeline Builder object types** | 在 Pipeline Builder 中创建的 object types **在分支上的 Ontology Manager 中不可修改** |
| **Indexing counts as a modification** | 对 object type 建立索引被视为一次修改。若该资源受项目策略保护，合并分支需要策略批准；要绕过该要求，可在合并前移除 indexing 改动 |
| **Reviewers apply across all ontology resources** | 给一个 ontology 资源加评审人会把他们加到整个 proposal（因为 ontology 改动被归在一起）。**只有位于某资源项目策略中的人，才需要批准该特定资源** |

### 4.4 Ontology proposals（审阅本体提案）

- **定位**：ontology proposal 类似于版本控制系统中的 **Pull Request**。它是把在独立分支上做出的改动**集成进 main 之前**进行评审与批准的机制。
- **创建时机**：对 global branches，创建 **Global Branching proposal** 时会**自动创建** ontology proposal，其中包含 reviews、名称，以及正在合并进 main 的改动的描述等元数据。对 **legacy ontology branches**，proposal 在**创建分支时**创建。

**Proposals 页签分组**：

| 分组 | 含义 |
| --- | --- |
| **My proposals** | 你创作的 proposal |
| **Assigned to me** | 你被指派为评审人的 proposal |
| **In review** | 进行中或已批准的 proposal |
| **Merged proposals** | 已合并进 **Main** ontology 的 proposal |
| **Closed proposals** | 已关闭且未被合并的 proposal |

**Proposal 内的页签**：**Proposal overview**、**Preview status**、**Review changes**、**Changelog**。

**进入方式**：
- 在 Global Branch 上：从 branch taskbar 选择任一 ontology 资源，然后选择 **View ontology proposal**；
- 在 **Main** 上：进入 **Proposals** 页签选择要查看的 proposal；
- 在 ontology 分支上：从导航 top bar 选择 **Open proposal details** 直接进入。

**Proposal overview 页**：集中展示 proposal 的阶段（stage）、改动、需要评审的 task、已选评审人。
- **查看分支上的改动**：改动显示在 overview 页底部，按**作者**与**task**分类（一个 task 对应一个 ontology 资源）。可查看改动、导航到该资源，或**从分支移除这些改动**。改动的历史也可通过 **Changelog** 页签访问，其中还显示改动的精确时间。
- **查看与添加评审人**：指派特定同事评审你的 proposal。
- **查看需要关注的 task**：该区显示 Review 阶段所有被拒绝（rejected）的 task。
- 可用 **Share** 选项复制 proposal 链接。

**Preview status 页签**：显示分支上哪些 object types 已被索引、正在进行中、或无法被索引。**一旦某个 object type 被索引，它就可以预览**，即其数据在你的分支上可用于查看与测试。

**Review changes 页签**：显示 proposal 中的所有 task。可执行的操作：
- 邀请更多评审人；
- 查看已迁移到 projects 的资源的审批策略；
- 对每个 task 单独批准/拒绝，或对所有合格 task 批量操作；
- 在 task 级别留下评论并与同事协作。

**Changelog 页签**：显示分支上改动的详细历史。task 可展开，显示某个用户在某个时间点做出的编辑；也可直接导航到相关 ontology 资源。

**Proposal 权限（四类）**：

| 动作 | 规则 |
| --- | --- |
| **查看 proposal** | proposal 的标题与描述对**所有能访问该 ontology 的人**都是可发现的。对 proposal 中某些资源至少有 **Viewer** 访问权的用户，可以看到与这些资源相关的改动 |
| **修改 ontology 资源** | 对某资源有编辑权限的用户可在分支上编辑它。对使用 **ontology roles**（而非 project permissions）的资源，**viewers 可在分支上提出建议（suggest changes）** |
| **在 proposal 中接受或拒绝 task** | 要让一个 task 被批准，批准人**默认**必须是底层资源的 **editor 或 owner**。若资源已迁移到 project 且受保护，批准人则必须依项目策略具备审批权限 |
| **合并 ontology proposal** | Ontology proposals 通过**合并 Global Branching proposal** 来合并。但对于 **legacy ontology branches**，**任何能查看该分支的人**只要获得所有必需批准即可合并 proposal |

### 4.5 Export / Edit / Import

**解决什么问题**：支持两类高级用户工作流：
1. 若你偏好**用代码做本体编辑**，可绕过 OMA 界面：导出 Ontology JSON 文件 → 在代码或文本编辑器中直接编辑 → 导入回平台；
2. 若你想把一个 Ontology 的**工作状态复制到另一个 Ontology**，可把当前状态导出为 JSON，再把复制的 JSON 导入平台（可在编辑器中做想要的修改）。

**导出**：从应用首页选择 **Advanced settings** 页，然后选择 **Export**。导出内容**包含你工作状态中的所有改动**。

**导入**：从应用首页选择 **Advanced settings** 页，然后选择 **Import**；会被提示从本地驱动器选择 Ontology 文件。选择 **Import** 后，会**从 JSON 文件重建整个工作状态**；应用 header 会显示文件中需要保存的改动数量。

**限制与报错**：
- 一个配置了 **conditional formatting rules** 的导出工作状态，**不能导入到它被导出的那个 Ontology 之外**的 Ontology。
- 报错 **`OntologyMetadata:UnreferencedRuleSets`**：说明你试图导入的工作状态带有该 Ontology 中未定义、因而无法转移的条件格式规则。需要先从这个工作状态中删除这些条件格式规则再导入。
- 文档在页首明确警告：**不应依赖导出的 JSON schema，因为它可能随时间变化。**

### 4.6 Usage（使用度指标）

**解决什么问题**：帮助本体编辑者**更安全地做改动**，通过更清楚理解改动的影响面（谁在用、用在哪个应用）。

**关键术语（原文定义）**：

| 术语 | 定义 |
| --- | --- |
| **Reads** | 当某个应用为指定 object type **加载对象**时记录一次 read。包括：在 Workshop 中把对象显示在表格里、为某 object type 返回搜索的全部对象、对某 object type 的某个属性做聚合，等等。**一次 read 代表一次对 Object Storage v1（Phonograph）或 Object Set Service（OSS）的加载请求**。一次加载或聚合并多对象只记为**一次** read。**Ontology Manager 中任何 object type 或 link type 的使用不计入** |
| **Writes** | 当某个应用作为 **Action、Function、Foundry Form、Object Explorer 直接编辑或 API 调用**的结果，对该类型对象做出编辑时记录一次 write。**一次 write 代表一次发送给 Object Storage v1（Phonograph）的编辑请求**。批量编辑许多对象只记为**一次** write |
| **Interactions** | 过去 30 天内对该类型对象的 reads 与 writes 总数 |
| **Active users** | 过去 30 天内触发过所记录 reads 与 writes 的唯一用户 ID 数量 |

**两个查看位置**：
1. **Overview 页签上的 usage 图**：过去 30 天使用情况的高层摘要，让本体用户能快速理解对该资源做破坏性改动的影响；
2. **专门的 Usage 页签**：资源的详细使用指标，可看到过去 30 天内**谁**使用了每个 object type、**何时**、在**哪些 Foundry 应用**中。也可通过点击 Overview 页签 usage 图上的 **See more** 进入 Usage 页签。

- **空 usage 图的可能原因**：若你预期有使用统计却看到 "No usage for the last 30 days"，可能是**内部表未配置**；文档建议联系你的 Palantir 代表。

**启用方式**：Overview 页签的 usage 与 Usage 页签的详细指标，都在 **Control Panel** 的 **Ontology settings** 页签中通过 **Ontology metrics** 开关配置。**该开关只能由 Ontology 管理员启用或禁用**，改动**最多需 60 分钟**在 Ontology Manager 中生效。

**共享 Ontology 的使用情况**：若你的组织与另一组织共享一个 Ontology，则 **Usage 页签可供所有已开启 Ontology metrics 的组织的用户访问**。显示的指标**只包含**对 object type **有访问权**的用户、以及来自**已启用 Ontology metrics 的组织**的用户的使用。

**角色小结（本机制相关）**：Ontology 管理员（Ontology administrators）——唯一可开关 Ontology metrics 的角色。

### 4.7 Cleanup（本体清理）

**解决什么问题**：做一个**安全删除 object types** 的工具。文档列出好处：没有多余 object types、更易导航的 Ontology；搜索与加载只在更少的 object types 上运行，Ontology 性能更好；不受多余存储成本负担。该工具旨在帮助本体编辑者判断删除某个 object type 是否安全，并提供一个 **deprecation（弃用）**选项以告知该对象类型的使用者其未来将被移除。

**访问与候选项生成**：该视图从工具首页访问。选择 **Start cleanup** 后，工具可能需要一些时间根据 Ontology 大小寻找清理候选。

**结果列表**：与其他首页列表页类似。可按特定 **flags** 或你负责的某个 **object type group** 过滤；可自定义表格显示的列。**默认按 object type 触发的 flags 中最高优先级排序。**

**三种处理动作**（选中对象类型后）：

| 动作 | 行为 |
| --- | --- |
| **Snooze** | 在可配置的一段时间内从你的清理队列中隐藏这些 object types。**Snooze 只影响执行该动作的用户本人** |
| **Deprecate** | 在所有显示对象类型状态的场景中把这些 object types 显示为**已弃用**。该选项告知用户迁移到其它 object types，或反馈该 object type 仍然有用。**可随弃用设置一个截止日期**，让用户知道还有多久必须停止使用 |
| **Delete** | 从 Ontology 中删除这些 object types，并**从对象存储中移除关联数据** |

- 对队列中某个 object type 采取动作后，它就从队列中消失；用表格过滤器查看你已经选过的所有动作。
- **弃用与删除的暂存方式与普通 Ontology 修改相同**。文档示例：`Work Item` object type 的对象带有用户编辑，因此只能被 deprecate，而另外两个可以被 delete。
- 右上角选择 **Save**，可直接把改动保存到 Ontology，或**创建 proposal 请求他人评审**。

**配置清理**：cleanup 页含一个子页，可自定义使用的 flags 及其各自的优先级。可选择**使用默认集合**或**自定义 flags**。
- 与 snooze 一样，这是**个人定制，不影响其他本体编辑者**。
- 保存改动并返回 **Cleanup** 主标签页时，会提示**重新计算清理队列**。
- 注意：若使用自定义 flag 设置，**未来新增的 flags 若在使用默认集合时是打开的，不会自动为你打开**。

**Cleanup flags（文档称此列表旨在回答常见问题，但并非穷举）**：

| Flag | 含义 |
| --- | --- |
| **Past deprecation date** | 该 object type 当前状态为 `deprecated`，且弃用日期字段已过 |
| **Trashed datasource** | 支撑该 object type 的任何数据源（dataset、restricted view 或其它）已在 Compass 中进入回收站 |
| **Datasource not updated in [x] days** | 通过 Compass 检查支撑数据源的最后修改时间 |
| **Description missing** | 该 object type 的描述为空。**不检查该 object type 所有属性的描述** |
| **Display name regex matches string** | 默认值 `\[test\|deprecated\]` 会匹配 display name 中含 `[test]` 或 `[deprecated]` 的 object types。例如组织常用 `UAT -` 或 `Testing -` 前缀标记处于用户验收测试的对象类型，则用正则 `UAT -\|Testing -` 找出所有匹配该模式的 object type。**支持 ECMA（JavaScript）正则语法** |
| **Phonograph deindexed** | **仅对 Object Storage v1 中的 object types 适用**。Object Storage v2 没有等价检查 |

### 4.8 Action log（动作日志 —— 改动可审计性）

**解决什么问题**：action log 把**成功的动作提交建模为 object types**，以便在对象感知的 Foundry 工具中分析与展示。可把一个 action log object type 作为决策类工作流的输入，并用于监控对 Ontology 的改动。

- **生成的对象类型命名**：显示名为 `[Log] <action type name>`，复数显示名为 `[Logs] <action type name>`。
- **能力分工表（原文，用于在多个"改动"能力间选择）**：

| 你需要回答的问题 | 应使用的能力 |
| --- | --- |
| 做了什么决策、由谁、何时、在什么情境下？ | **Action log** |
| 这个对象上的每一次编辑的完整历史（无论编辑如何发生）？ | **Edit history** |
| 这个动作成功或失败的频率，以及耗时？ | **Action metrics** |
| 如何撤销某个 action 施加的编辑？ | **Undo or revert actions** |
| 当某个 action 开始失败时如何收到告警？ | **Monitoring** |

- **两条需直接说明的后果**：① action log **只记录成功的动作提交，不记录失败**；失败由 **Action metrics** 跟踪。② action log 记录的是**通过 action types 做出的编辑**；在 action type 之外施加的编辑（例如直接写 backing datasource，或 legacy Foundry Forms writeback）**不会产生 action log 对象**。**区分的是路径而不是客户端**：通过 API 或 SDK 应用的 action type 与在 UI 中一样会产生 action log 对象，Object Explorer 的 **inline edits 是 action-backed 的，因此会被记录**。

**配置位置（OMA 中两处独立配置）**：
1. **为单个 action type 生成 action log 对象**：打开该 action type → **Capabilities** 页签 → 找到 **Create action log objects** 区（界面描述为 *Generate an object every time this action is triggered successfully*）→ 启用开关 → 选 **Generate object type** 创建支撑的 action log object type。
2. **要求每个编辑某 object type 的 action 都带 action log**：打开该 object type → **Datasources** 页签 → 找到 **Edits** 区 → 启用 **Only allow Action types with action logs**（界面描述为 *All actions that edit objects of this type will need an action log in order to function*）。
   - 该开关**在对象类型已启用 edits 前是隐藏的**；找不到开关时应先在对象类型上启用 **Allow edits** 并保存改动，再回到 Datasources 页。**把 Allow edits 关掉也会清除该设置。**

**Action log 的本体结构**：
- action log object types 与 action types **一对一映射**。提交一个 action 会生成对应 action log object type 的**一个新对象**；该新对象**自动链接到这次提交的 action 所编辑的所有对象**。
- 设计理由：通过与 action types 一对一建模，action log 能捕获超出具体对象编辑的情境信息，例如同时被编辑的其它对象，以及动作提交时世界的状态（以 Ontology 表示）。
- 例子：一个 `Close Alerts` action type 把多个选中 `Alert` 对象的 Status 属性改为 "Closed"；配置 action log 后，一次关闭 10 个 `Alert` 对象会产生**一个** action log 对象，并带指向全部 10 个 `Alert` 对象的外键链接。
- 权限：要应用一个 action log 支持的 action type，用户需要 action log object type 的相应权限，就像该 action type 通过 rules 与 functions 可能创建或修改的任何其它对象类型一样。

**Action log schema**：
- **Summary 区**（位于 Values to log 之上）：保存一段可自定义的字符串描述该动作。界面描述为 *Add a human readable summary of what happened. You can reference parameters by hitting `/`*。
- **Values to log** 分 **Required values**（不可从配置中移除）与 **Optional values**。
- **Required values** 包含：Action RID（单次动作提交的唯一标识）、Action type RID、Action type version（每次 action type 更新自动递增的版本号）、Current timestamp（提交的 UTC 时间戳）、Current user（提交用户的 Multipass 用户 ID）、Edited objects（该动作编辑的所有对象的主键值；**不支持存储除主键外的被编辑对象属性**）。
- Required values 还包含**副作用与撤销的溯源信息**，用于审计改动原因：动作调用的 webhooks 标识（同步与异步）、动作发送的通知标识与被通知用户、动作所应用到的 **scenario** 的 RID（若有）、以及该动作是否被撤销及撤销的用户与时间戳。
- **Optional values** 包含：参数值；object reference 参数的属性值（**若该 object reference 参数启用了 allow multiple values，则不支持**）。
- action log object types 可配置存储**并非由该动作编辑**的对象属性。这样既能存数据编辑，也能存关于本体编辑情境或动机的相关信息。例子：`Alert` 对象还有 Priority（High/Low Priority）、Created at、Source machine 属性；即使它们不被 `Close Alerts` 编辑，action log 也支持存储它们。通过对 Priority 聚合而不编辑该列，就能回答「大多数 High Priority 告警的来源在哪里？」或「关闭 High Priority 告警需要多久？」。

**限制与约束（原文表）**：

| 约束 | 详情 |
| --- | --- |
| **Property types are fixed once created** | action log 属性的类型在属性创建后**不可更改**。若该日志映射的来源属性类型后续变化，action type 会**校验失败**。恢复方式：用新类型新建一个 action log 属性，并更新映射引用它 |
| **Summary length** | 一个 action log summary 最多接受 **20 个部分**。每个字面文本部分最多 **50 个字符**。**该长度限制不适用于参数部分** |
| **Summary content** | action log summary **不能引用 object type 参数** |
| **Object reference parameters** | **只有单值 object reference 参数**才能为日志贡献属性值。启用了 allow multiple values 的参数不行 |
| **Media reference parameters** | 使用 media references 的参数被排除在 action logs 之外 |
| **No backfill** | 启用 action log **不会**为已经提交过的动作创建日志对象。**记录从保存该配置的那一刻开始** |
| **Edit limits** | action log 对象受与其它对象编辑相同的 **scale 与 property 限制** |

- **函数支持的 action type 上的 action log**：要为 function-backed action type 配置 action log，其背后的 Ontology edit function **必须配置 `Edits` provenance**。
- **时间线查看**：可在 Workshop 中用 **Action Log Timeline** widget 以时间线查看 action log object types；配置时间线以支持数据审计并回答「什么变了、由谁、何时？」。在 Workshop 中，action log object types 可**union 在一起**，用于某用例内或跨 Ontology 的整体编辑视图。配置方式：选择被编辑的 object type，然后选择要显示哪些 action log object types 及其属性。Action logs 也可与**对象评论**一起显示在单个 feed 中，通过 **Comments** widget。
- **排障消息（原文表）**：

| 消息 | 含义与解决 |
| --- | --- |
| **Action Log required but not enabled** | 某个 action type 没有 action log，但它编辑的某个 object type 要求 action log。在该 action type 的 **Capabilities** 页签启用 **Create action log objects** |
| **Associated object type is missing. Logs are not being recorded.** | 支撑该配置的 action log object type 已不存在，因此没有日志被写入。选择 **Generate object type** 新建一个 |
| **Action log has no writeback dataset defined** | 该 action log object type 没有 writeback dataset，因此无法存储日志对象。为该 action log object type 配置 **Writeback datasource** |
| **This property will not be used for logging until indexing is complete.** | 新加的 action log 属性正在等待索引。该属性的记录会在索引完成后开始 |
| **Function has no Edits Decorator** | 支撑该 action type 的 function 未声明 **`Edits` provenance**，而 action log 需要它 |
- 补充：一些平台消息会提到 **action log rule**，这与 action type **Capabilities** 页签上的 **Create action log objects** 区**是同一个配置**。

### 4.9 动作治理细节：Submission criteria 与 side effects

**Submission criteria（提交条件，旧称 validations）**：
- **定义**：决定一个 action 是否可以被提交的**条件**。文档明确其作用：**把业务逻辑编码进数据编辑权限（encoding business logic into data editing permissions）**，从而确保 Ontology 数据质量与编辑治理。
- 由**条件（conditions）**与**算子（operators）**组合而成；条件是对两个值的单次比较，算子用于组合与嵌套条件。**只有当所有 submission criteria 都满足时，动作才能被提交。**
- **与权限的区别**：这与「治理用户能否编辑该 action type 本身」的权限**相互独立**。一个 object type 可以有多个 action types 增删改对象，**每个 action type 有独立的 submission criteria**。
- **三种条件模板**：**Current user**、**Parameter**、**Execution context**。
  - **Current user**：基于提交动作的用户定义权限。可检查用户 ID、通过 group IDs 检查组成员关系、或任何可用的 multipass 属性（如用户所属 Organization）。Foundry 把用户 ID 当字符串求值，可与静态定义的用户 ID 列表或任何存储用户 ID 的字符串参数比较。group IDs 选项使用动作用户所在组（**包括直接与继承的成员关系**）。Multipass 属性被视为字符串列表，只能与其它字符串或字符串列表比较。通过 **Other user attribute** 字段，可针对用户无权访问的属性配置条件；**若用户对某属性没有访问权，该条件会失败**。
  - **文档明确警告**：**避免对 group、marking 或 organization 成员关系使用 NOT 条件**。文档说明这是**错误配置**：平台支持**受限令牌（scoped tokens）**，它只携带用户权限的一个子集；这些令牌可能缺少 NOT 条件所要检查的属性，导致条件通过并授予超出预期的访问权。
  - **Parameter**：可使用参数区中定义的参数。参数由其它应用或用户传入 action type。对参数设置条件可把业务逻辑嵌入 action type，阻止用户对不符合业务要求的数据提交动作。
  - **Execution context**：可基于动作提交被求值时的执行情境，即该动作**是否在 Ontology Scenario 中提交**。Scenario 执行情境只表示动作在 Ontology Scenario 内被求值，**不标识具体哪个 Scenario**。
  - **不支持**：Submission criteria **不支持 attachment 与 object set 参数**；这两类参数会从选择面板中被移除。
- **算子**（按参数类型预过滤展示；**改变参数时，所有使用该参数的条件都需要重新配置**）：
  - 单值参数：`is`、`is not`、`matches`、`is less than`、`is greater than or equals`（文档表格中列出的算子条目）。
  - 多值参数（object reference 列表会被转成值列表——对象值或所定义属性的值）：`includes`、`includes any`、`is included in`、`each is`、`each is not`。
  - **逻辑算子**：可组合不同条件，也可嵌套以构成更复杂逻辑，可要求其下全部、任一或没有条件满足才通过。
- **失败消息（Failure message）**：用于定义 Action 无法提交时应显示什么错误。**每个根级条件与逻辑算子都有自己的失败消息**；若下层条件不满足，则显示对应根级（父级）的失败消息。失败消息会在 Foundry 各处（Object Explorer、Workshop、Quiver）在条件不满足时展示给终端用户，告知其为何被阻止提交。
- 可用 OMA 中的 **test run** 针对给定参数值组合验证 submission criteria 的求值结果（也用于验证 rules 与最终编辑结果）。

**Side effects（副作用）**：
- 设计目的：action types 旨在支持组织内**全范围的决策过程**。当 Ontology 作为某决策过程的**记录系统（system of record）**时，用 rules 定义对象修改可以极灵活地表达业务流程。为支持完整流程，还支持两类附加特性：实时流程中需要**通知（notify）**用户系统中正在发生的变化；当 Foundry 之外的系统是事实来源时，需要**集成（integrate）**外部系统以支持既有业务流程（有时称为 **decision orchestration**）。
- **两类主要副作用**：
  - **Notifications**：灵活配置动作被应用时如何通知用户，包括向平台上的用户发送 email。
  - **Webhooks**：以高度灵活的方式连接 Foundry 之外的系统，包括向 REST API 或 ERP 系统发送请求。由此可写入组织内其它源系统，或通过与消息系统集成更灵活地通知用户。

**Action types 基础定义与写入路径**：
- **Action**：一次单一事务（a single transaction），基于用户定义的逻辑，改变一个或多个对象的属性。
- **Action type** 定义中包含「动作提交时发生的副作用行为」。
- 文档给出的教学例子：`Assign Employee` action type 定义用户如何改变某个 `Employee` 对象的 `role` 属性值；可要求参数定义让用户以标准化表单输入新角色，并可包含自动在 `Employee` 与新的 `Manager` 对象之间创建链接的规则；还可以包含通知旧、新经理的 notification 副作用，并校验只有 HR 等授权员工才能执行该动作。
- **一致性保证**：对 objects、property values 与 links 的任何改动都会在用户执行动作时提交到 Ontology，并反映在所有用户应用中；同样的动作逻辑与校验可在所有面向用户的应用中使用，确保对 Ontology 的一致编辑。
- **writeback dataset**：包含用户编辑在内的最新版本对象数据会被捕获在对象类型的 **writeback dataset** 中。
- **前置配置要求**（入门文档）：用户要能执行 action type 中定义的动作，需要**额外配置**——若运行 Object Storage v2，用户必须通过开关启用 edits；若运行 Object Storage v1（Phonograph），必须创建 **writeback dataset**。文档注明 **Object Storage v1 处于计划弃用（planned deprecation）阶段，应迁移到 Object Storage v2**。
- **创建向导步骤（入门）**：初始化向导含若干步——Action type 步（打开 **Object** 页签 → 选 object type → 在 **Object actions** 下选 **Modify object(s)**）、Mapping 步（**Add property** 添加要改的属性）、Metadata 步（填 **Action type name**）、最后一步选 **Create**。
- **参数补充**：参数是 action type 的**输入**，是 Rules 与其它 Foundry 应用（如 Workshop、Slate、Object Views）之间的接口；参数像变量一样承载外部值，每个参数由类型定义。每个参数可单独配置是否在表单中暴露、是否可由用户修改。可用 **value type** 约束 action 参数，从而在 Foundry 中复用校验规则。参数可被 rules 引用以把值传回对象、链接或副作用；可用于 submission criteria；可访问对象属性被动作改变前的当前值；也可用于 **overrides** 改变后续参数的配置。
- **冲突解决（用户编辑 vs 数据源更新）**：Ontology 中的对象实例既可被输入数据源创建和修改，也可被用户编辑/动作创建和修改。**当单个对象实例（即具有特定主键值的行或对象）同时从输入数据源与用户编辑收到数据时，这些收到的值必须通过冲突解决策略被透明地解决。** 两种策略：**Strategy 1: Apply user edits（默认）**；**Strategy 2: Apply most recent value（可能在你所属的 enrollment 上不可用）**。
- **Function-backed actions**：action type 中的 **rules** 定义对象在动作被应用时应如何变化；许多 action types 可用简单规则定义（创建、修改、删除对象，或在对象间创建与删除链接）。但简单规则不足时（例如：修改当前相互链接的多个对象——把 `Incident` 设为 Closed 同时把所有链接的 `Alert` 设为 Resolved；基于更复杂逻辑读取多个对象计算值再写入属性；创建多种类型的对象并建立它们之间的链接），可把 action type 配置为调用一个 **function** 来定义对象应如何被修改。这类 action types 常称为 **function-backed actions**。文档提示：function-backed action types 虽灵活，但同时受 **action type limits** 与 **function execution limits** 限制。

### 4.10 角色汇总（本文所涉文件可确认的）

| 角色/权限主体 | 文档依据 |
| --- | --- |
| **Ontology roles** | Ontology 的中心权限模型；与 Foundry 文件系统 roles 类似；可授予在 **Ontology 级别**或**单个资源级别** |
| **Ontology administrators（Ontology 管理员）** | 唯一可启用/禁用 **Ontology metrics** 开关的角色 |
| **Viewer（至少）** | 对 proposal 中某些资源至少有 Viewer 访问权即可看到这些资源的改动；对使用 ontology roles 的资源，viewers 可在分支上**提出建议** |
| **Editor / Owner（资源）** | 默认情况下要批准一个 task，批准人必须是底层资源的 editor 或 owner；有编辑权限的用户可在分支上编辑该资源 |
| **Approval rights（审批权）** | 资源迁移到 project 且受保护时，批准人须依**项目策略**具备审批权；具有审批权限的用户即使未被加为评审人也可批准 proposal |
| **Reviewer（评审人）** | 通过 branch taskbar / Global Branching proposal 页 / ontology proposal 页添加；给一个 ontology 资源加评审人会加到所有 ontology 资源；评审人列表用于跟踪，而非限制批准 |
| **Builder / end user** | 应用层面的两类用户群（workflow-specific 应用需要 builder 预配置）；Quiver 的 Analytical 模式与 Dashboard 模式分别对应 walk-up usable 与 customizable |
| **权限变更/迁移状态** | 本体资源必须**先迁移到 project permissions** 才能被保护；legacy ontology roles 与项目权限并存于文档表述中 |

---

## 5. 图与探索

> **前置说明**：本次所列文件中**没有**任何一处直接对 Vertex 与 Object Explorer 做对比。下文的差异是从两者各自文档的定位、工作流风格、配置模型与交互原语中提取的，属于对文档陈述的归纳，而非文档给出的对照表。

### 5.1 Vertex：图能做什么

**启动与新建**：
- 从 Foundry workspace 侧边栏 **Apps** → **Operational Applications** → **Vertex** → 点 `+ New Graph` 图标。
- 新建探索会打开空白工作区，可选择 `+ add objects` 开始；从对象搜索弹窗中选择要探索的对象。

**对象与关系探索**：
- **对象选择面板**：点击图上的对象会自动打开选择面板显示其属性。面板右下角的 **`(+)`** 可添加 **derived property functions**（示例：一个简单函数计算与某机场相关航线上告警总数）。**derived properties 显示在选择面板顶部。**
- **对象节点标签**：对象可在节点标签中显示关键信息或指标（示例：航班的起飞与到达时间）。
- **Search Around（右键）**：从单个节点或一组节点右键，可看到选择、布局与探索选项；从相关对象列表中选择即可把其加入图。下拉列表中显示每类对象的**总数**。对象数量很大时应考虑使用数量旁的**过滤图标**加额外过滤，这会打开 **Search Around 面板**，可在其中加过滤器并跨多步搜索。
- **多步 Search Around**：当需要建立跨不同对象类型的多步、带过滤的图时，Search Around 面板提供点选界面在生成新图的过程中构建逻辑。入口：基础 Search Around 下拉列表中的过滤图标，或工作区右侧的页签。开始方式：选择单个对象或同一类型的多个对象，然后通过选择一条 **link** 从选择集创建 Search Around。
  - **Set starting objects**：若想更新起始对象集，选择新的对象（或对象组）并点击悬停在 starting objects 框上时出现的 **Set starting objects**。
  - **Find related objects**：选定要加入的相关对象后，结果对象类型旁会显示找到的对象数量。要进一步过滤返回对象，点 **Add filter** 并选择用于过滤结果集的属性。
  - **Add link**：过滤后可选择立即加入图，或用 **Add link** 继续构建跨多个对象的多步 Search Around。**下一段 link 会以前一段 link 的结果集作为其起始对象集。**
  - 过滤器语义细节：一旦应用了过滤，**起始对象集会被过滤为那些与过滤后的结果对象集相连的对象**（示例：157 个航班飞往纽约州机场）。
  - **Add to graph**：根据 Search Around 面板中定义的遍历生成新图；视复杂度可能需要一些时间。
  - **参数**：为增强 Search Around 的可复用性，可定义参数并在整个 Search Around 中使用。点面板右上角 **View parameters** 查看已有参数或创建新参数；点 **Add parameter** 选择要添加的参数类型。添加后可给值，或点编辑按钮修改其名称、描述与**默认值**（加载该 Search Around 时使用的默认值）。随后可在任何类型合适的过滤字段中使用该参数：打开过滤字段旁的 **parameter toggle**，再从下拉中选参数。改变参数值时，Search Around 会更新所有使用该参数的处。
  - **保存与加载**：若想在其它图或图模板中复用该 Search Around，可将其保存为资源——在要保存的 Search Around 页签旁选择下拉，弹出模态框中选择名称与保存位置。加载：在 Search Around 页签 header 的 `+` 图标中添加新 Search Around 时，选择 **Load Search Around** 会打开资源选择器；加载后会被提示从图中选择对象作为起始对象集。**只有类型合适的对象才能被选中。**
- **Histogram filters**：建立好对象图后，可用直方图过滤探索图。直方图显示所选对象的属性并提供各值总数；在直方图中的选择会反映到图上，带来更细粒度的探索。
  - 在**只读模式**下，可用侧边栏的 **Histogram** 页签按对象类型与属性过滤图视图。选定感兴趣对象后，可选 **Filter to** 或 **Filter out** 把直方图选择应用到图。图画布顶部显示已应用的过滤器；可点个别参数旁的 `x` 移除单个对象过滤，或选 **Clear filters** 移除全部。
- **关联事件**：若对象有关联事件，可配置为显示在受影响对象上的 **badge**。点击带相关事件的对象节点，可在 **object selection 侧边栏的 Events 页签**查看详情。
- **随时间理解当前状态与变化**：对象可**按对象类型、属性值、时间序列或事件**设定样式。文档示例：Airport 着深蓝；Flights 着浅蓝，当 `Cancelled Status` 为 `True` 时显示红色；Flight Delay events 着红；Flight Delay events 作为红色 badge 显示在 Flight 对象节点上。用 **time selection panel** 可以「scrub」（拖动游标）以**动态样式**看到属性如何变化；事件 badge 只在事件进行中（事件起止时间之间）出现。
- **探索对象关系（更探索式的工作流）**：在对象图的**可编辑视图**中，可使用完整 Vertex 应用中的许多操作，包括 Search Around、样式与布局变更。**在 Workshop 模块中对图所做的改动不会更新生成该图的底层模板；若想永久改变 Workshop 中的视图，需要更新底层模板。** 图工具栏的附加探索工具栏可看到相关操作。
- **布局（自动布局选项）**：工具栏有若干预定义布局选项，选中后对象与边自动移动。多数布局有高级参数，点相应布局旁的齿轮图标访问。**Auto 与 Circular 没有高级参数。**

| 布局 | 高级参数 |
| --- | --- |
| **Hierarchy (Left to Right / Top to Bottom)** | **Reverse**：反转层级顺序（左右变右左、上下变下上）；**Root nodes**：选择占据层级根的节点；若选 **Automatic**，会基于边方向为你选一个根节点 |
| **Grid** | **Staggered**：可偏移奇数行元素；**Grid dimensions**：约束网格的行数或列数，**Automatic** 模式会尝试使用相等的行列数 |
| **Horizontal Row / Vertical Column** | **Order by**：用于排序节点的对象属性，默认升序。若未选 Order by 属性，布局维持既有的水平（行）或垂直（列）节点顺序。**分组节点与任何由不含指定属性的对象支撑的节点，升序时放在开头，降序时放在末尾。只有数值属性会出现在该下拉列表中。不同对象上同名的属性会被一起排序。** **Reverse**：在升序与降序间切换，仅在选择了 Order by 属性时出现 |
| **Radial** | **Central node**：指定应出现在布局中心的节点；**Density**：1 到 5（含）之间的值，决定节点间距 |
| **Cluster** | **Cluster by**：指定用于聚类的属性；若未选属性，则**按对象类型聚类**。分组节点与任何不具备所选属性的节点会被聚在一起。**只有带 `Selectable` 或 `Low Cardinality` render hints 的属性才出现在该下拉中。不同对象的同名属性会被聚在一起。** |
| **Cartesian** | **X/Y property**：用作节点 x、y 坐标的属性。坐标会被归一化，使节点在执行布局时能放进视口。**除非选择了 x 属性、y 属性或两者，否则不会执行 Cartesian 布局。** 分组节点与不具备所选属性的节点保持布局前位置。同样只显示带 `Selectable` 或 `Low Cardinality` render hints 的属性；不同对象的同名属性会被一起排序。**X/Y reverse**：反转 x、y 坐标，仅在做出属性选择后出现 |

- **分组节点**：
  - **按对象类型分组**：选中要分组的对象，用工作区顶部布局工具栏分组或取消分组。分组后可在左侧选择面板看到被分组对象的完整列表。只想取消分组其中一部分时，用选择面板选中那些对象并选 **Ungroup**；也可用直方图的 **Filter to** 功能实现。
  - **按对象类型某属性分组**：用直方图探索所选对象属性，并**按显示的值分组**对象；这会改变图上对象布局以反映新分组。
  - **把节点分组进边（Group nodes into edge）**：某些对象是事务型的，会在系统中其它节点/对象之间移动。例如 **Flight** 作为事务型对象在 **Departure Airport** 与 **Destination Airport** 之间移动。此时可把订单类对象分组到边上，并能基于关键属性/指标为边设样式。**可以在 Ontology Manager → Capabilities 页签中自动把事务型对象分组到相关边**（即 **link merging**）。选中边并从右键菜单选择 **Ungroup** 可显示此前分组在边中的所有对象；也可先用直方图或选择面板选中要取消分组的子集再取消。
- **边方向（Ontology 层配置）**：添加链接到图时，**默认边箭头从 link 的右侧指向左侧**。例如对配置为 many-to-one 的 link type，箭头会从 one 侧指向 many 侧。可**按 link type** 用以下 Ontology type classes 配置：
  - **Primary Direction**：`kind: vertex`，`name: link_primary_direction`——放在 link 的一侧时，表示边箭头应指向该侧的 object。
  - **Undirectional**：`kind: vertex`，`name: link_undirectional`——放在 link 任一侧时，表示边上不显示箭头。
  - **Bidirectional**：`kind: vertex`，`name: link_bidirectional`——放在任一侧时，表示边两侧都显示箭头。
  - **边箭头也可按图隐藏或反转**，用 layer styling 选项。
- **层级样式（Layers）**：Layers 指同一对象类型的对象节点、或节点之间的边关系。可在左侧 sidebar 的 **layer styling 面板**中逐个为节点与边设样式，或**按对象属性及相关时间序列/测量值**设样式。layer styling 可可视化关键信息、计算指标，并按**参数化条件**设样式以展示当前或模拟的系统状态。
  - **对象样式**：点要配置的对象类型旁的 **Styling Options** 打开样式菜单。
    - **Color by**：选 **Fill Color** 下拉以选择用于设样式的参数以及该层所有对象的颜色。**可选时间序列 measure 作为 Color by 参数**，它会根据所选时间窗口动态更新样式。也可用 **derived property functions** 为节点着色。
    - **Subtitle**：可给该对象类型下每个对象、或对象的某个所选属性添加副标题。副标题会显示在图上同类型的所有对象上。
    - **Extended labels**：可选 **Extended Labels** 为所选对象节点添加特定读数。可从**真实世界时间序列读数或模拟值**中选择，从而在单一视图中比较当前与建模条件。设好 extended label 样式后，可从工作区左侧的对象选择面板选择要显示的属性或时间序列。
    - **Badges**：添加 badge 以指示与特定对象类型相关联的事件数量（示例：一个 delayed flight event）。
    - **Node style**：可选择把对象显示为默认节点，或显示为完整 object card。
  - **边样式**：边表示对象间关系，可设样式以可视化系统中节点之间或流程中的交互。点要配置的边上的 **Styling Options**：
    - **Line color**：可基于对象类型或相关对象的共同属性设置边颜色；
    - **Line type**：可把线设为直线、曲线或正交；
    - **Labels**：当有对象被分组在边中时，可基于对象单个或聚合属性配置标签以显示关键指标；
    - **Line width**：可基于对象属性给边应用不同宽度；不同线宽可指示对象之间（如机场）的交易（如航班）流动与体量；
    - **Badges**：与对象节点一样，可为特定边关系添加 badge 表示关联事件数量（示例：一个 delayed flight event）。
  - **Saved styles（已保存样式）**：配置后可为同一张图保存不同样式选项，以提供系统的不同视图。文档示例：可把若干机场之间的航班配置为按航空公司承运人的关键绩效指标设样式，然后用同一张图的不同样式显示相同航线上的客户满意度。
  - **Saved selections（已保存选择）**：可把图上选中的对象组保存为一个 saved selection。做法：选择包含目标对象的任意数量节点与边，然后在右键菜单或工具栏的 **Selection** 菜单中选择 **Save objects in current selection**。
    - 每个 saved selection 有相关名称与颜色，出现在 layers 面板的 **Saved selections** 区。
    - 图上的每个对象（以边或节点表示）会有一圈由其所属 saved selections 颜色组成的**分裂边框**。**每个对象可属于任意多个 saved selections，但边框只显示前三个 saved selections 的颜色。**
    - 快速选中某个 saved selection 中存储的所有对象：悬停在该 saved selection 上时选择 quick select 动作。
    - 可在 layers 面板编辑 saved selection：改名称——选名称、输入新名并按 Enter；删除或改颜色——悬停时点 `...` 图标；每个 saved selection 的边框可**用眼睛图标开/关**。saved selection 中的对象可通过在图上选对象、点 `...` 按钮，然后使用 **Add selected objects** 或 **Remove selected objects** 来编辑。
- **在 Workshop 中的限制**：**在 Workshop 模块中对图做的改动不会更新生成该图的底层模板**；**在 Workshop 模块中对样式做的改动不会被持久化**；但可在底层模板中配置多个 **saved styles**。

**图模板（Graph templates）**：
- **定义**：Vertex graph templates 是**基于参数生成带定义样式的图**的资源。支持的工作流：
  - 把一个对象/对象集上的图分析 **pivot** 到另一个对象/对象集；
  - 创建一个可复用资源，为消费者编码一套图生成工作流；
  - 把图模板**嵌入另一个 Foundry 应用**，例如 Object View 或 Workshop 应用。
- 任何 Vertex 分析都可以转换为图模板。把分析转成模板能让未来同类分析更容易进行。
- **转换方式**：在右上角工具栏打开 save 选项，选择 **Save as Template...**。会打开一个带 **Configure parameters** 选项的助手。
- **两类模板参数**：
  - **object parameters**：模板的对象输入，在模板被使用时会被加入图。添加 object parameters 还允许对模板用户提供的对象执行 Search Around 与函数。
  - **non-object parameters**：可作为自定义 Search Around 函数或已保存 Search Around 的参数的附加参数。支持的类型与 Search Around 函数支持的非对象参数一致。
- **配置 Search Arounds**：每个 object parameter 可关联 Search Around，类型可以是使用 Ontology links 的**简单 Search Around**、**Search Around 函数**、或用 Search Around 侧边栏构建的**已保存 Search Around**。对 Search Around 函数或已保存 Search Around 的任何非对象参数，可映射到一个值，该值**可以是常量或参数**；要映射到参数，点输入框左侧的参数按钮并从下拉选择。
- **配置 layers**：可配置与模板相关的 layers 与 layer styling。**Styling layers 会保存图上当前的样式**；**Excluded layers 会在保存的模板中省略该 layer 样式**。
- 最后：选择要应用的布局、选择要从当前分析保留哪些图的设置，然后查看 **template summary** 并保存模板。
- **使用模板**：模板打开后会被提示为模板参数提供值。也可用 URL query 参数预载对象或对象集：对象用 `objectRid=<your_object_rid_here>`；对象集用 `objectSetRid=<your_object_set_rid_here>`。要操作给定参数值，用顶部工具栏的 **Parameters** 按钮——可选择用作某个 object parameter 值的所有对象，或改变参数值以重新生成图。
- 模板也可**通过 Vertex widget 嵌入 Workshop**。

**Link merging（`vertex__link-merging`，全文仅 15 行）**：
- 在 Ontology Manager 的 **Vertex Ontology Capabilities** 区配置 **Link Merge**，可让对象**被自动分组进两个节点之间的边**。该配置有助于**可视化节点之间的事务流**，并**简化图生成**。
- 用户可通过 **Search Around 菜单中的 `link via` 选项**访问。

### 5.2 Object Explorer：探索能做什么

**搜索**：
- 从 Object Explorer 首页用全局搜索栏搜索，结果显示在搜索页：查询在搜索栏可见且可编辑；页面按页签划分：默认显示 **All** 页签（含所有结果）；匹配结果可被过滤进 **Objects**、**Object types**、**Artifacts** 三个页签。
- 搜索页还含**侧边栏**导航。结果按类型归类，左侧导航菜单帮助在不同类别间移动；点任一区块标题也会把结果过滤到该类型，若结果多于 All results 视图中默认显示数量，会显示该类型的全部结果。
- 侧边栏区块：**All results**（默认激活，显示各类别的匹配样本）→ **Object type filters**（点任一项显示该 object type 的更长的匹配列表；点区块底部 "View X other filters >" 会从 All 切到 **Objects** 页签）→ **Object type groups**（按关联 group 过滤结果；点底部 "View all filters >" 会从 All 切到 **Object types** 页签）→ **Artifacts**（分为 "Explorations & Lists"、"Comparison Views"、"Modules" 三类；点底部 "View all filters >" 会切到 **Artifacts** 页签）。
- **搜索范围**：Object Explorer 搜索栏会搜索平台中**所有 Objects**，以及对象相关资源如 **Object types**、已保存的 **Explorations、Lists、Comparisons、Modules**。
- **隐藏对象与属性类型永远不会**作为搜索结果出现，也不会出现在 Object Explorer 的任何其它位置。
- **结果排序规则**（在单个对象结果区内）：所有 prominent object types 显示在非 prominent 之前；在 prominent 与非 prominent 各自内部，object types 按其**个体对象结果数量升序**排序。即：结果数最少的 prominent 类型先显示，然后是结果更多的 prominent 类型，接着是（相对于其它非 prominent 类型）结果最少的非 prominent 类型，依此类推。
- **从单个结果出发探索链接对象**：对单个对象的匹配结果，**悬停**在该结果上会给出**沿某条特定 link 开始对象探索**的选项。示例：搜索机场 "SFO"，可悬停该结果并从「到达该机场的航班」开始探索。

**Pivot 沿链接跳转**：
- 在做探索时，可以把探索的主对象类型**切换到任何链接的对象类型**。
- 文档示例问题：如何找出未来 30 天从美国东部大型机场起飞的所有航班？文档给出两种思路：一是从 Flights 探索开始、按链接机场的属性过滤（Filtering on Linked Properties）；二是从 Airports 探索开始，把机场过滤为美国东部且拥有较多唯一承运人的机场，然后**点右下角 "Linked Objects" 区的 Departing Flights 选项来 pivot**。pivot 后探索的主对象类型变为 **Flights**，并被过滤为只包含从先前过滤出的大型东部机场起飞的航班。
- 文档明确：探索的结果不再是 Airports 而是 Flights（见右侧预览面板）；**可以连续跨多条链接 pivot**，从而灵活地跨本体探索。

**对结果集执行动作与其它操作**（Exploration 中右上角按钮分三类）：
- **"Actions"**（数据 writeback）：先显示 Ontology 中配置好的 **action types**，带名称与描述。选择一个会打开表单以填写参数并提交动作。**当前探索中选中的对象集（若未选中则为全部对象）会直接传入表单**，因此只需配置其它参数。**若选中对象数量超过 1000，Actions 不可用。** Object Explorer 会用相关选中对象**预填**动作参数；**若对某个参数该填什么存在不确定性，决定权留给用户，不提供预填**。
- **"Open In"**：若存在把当前结果集在另一应用中打开的方式，会显示在该标题下。
- **"Export"**：导出对象集的方式（如导出到 Excel、或把对象 ID 复制到剪贴板）出现在这里。

**结果视图（Results View）**：
- 以表格视图显示探索中的对象；向下滚动可加载更多对象。
- **按列排序**：结果表可按带 **`Sortable` renderHint** 的属性排序；点列头的下拉箭头按该列排序。一旦某列被用于排序，其列头会显示排序图标；若选了多列排序，**最后选的那列优先**，此前的排序图标旁会带数字显示排序顺序。下拉中的 **"Clear All Sorts"** 可把排序重置为原始状态。
- **列配置**：
  - **改变列顺序**：拖拽列头上的 handle 图标。
  - **冻结列**：从列头下拉选择 "Freeze X columns" 保持最左 X 列在向右滚动时可见；**复选框列计入该数量**。
  - **调整列宽**：拖拽列头右侧（高亮为蓝色的边界，位于配置下拉的右侧）到目标宽度。
  - **添加与移除列**：从列头下拉选 "Hide this column" 隐藏单列；选择 "Configure columns" 打开配置菜单，一次重排和配置多个列。左面板显示表格的默认列，右面板显示所有可能列的当前顺序与可见性。可用快捷键按钮隐藏或添加所有列，或用顶部搜索栏搜索特定列来切换可见性。拖拽列到目标位置改变顺序，或用下方菜单把列移到顶部/底部。选择 "don't truncate text in this table" 会让文本属性在无法在现有列宽显示时换行到下一行。用右下角按钮保存配置。**管理员可把当前视图保存为新 layout 并设为所有用户的默认**，从而更新该表的默认配置。
- **预览结果**：点某行的 **Title 列**会在新的 Object Explorer 页签打开该对象的 object view；通过点复选框或该行的任何其它列选中一个或多个对象，会在当前 Results 页签**打开该 object view 的预览**。选中对象后，**Selection Preview 面板**从右侧打开；要获得完整表格视图，用面板左上角的 collapse 图标关闭它。**若选中多个对象，前二十个中任意一个的 object view 都可预览**，显示在 object view 上方的一列卡片中。要一次比较两个对象的 object view，选右上角下拉并选 **"Compare objects"**。
- **查看时间序列属性**：时间序列属性可与常规属性一起在 Results View 中查看。**时间序列属性是存储带时间戳的值历史的对象属性。** 示例：`Country` 对象含三个时间序列属性（COVID19 New Tests / New Deaths / New Cases），每列左侧显示时间序列中最近一次观测，右侧显示可视化的 history 的 **sparkline**。
- **Inline edits（行内编辑）**：配置了 inline edit action 的属性可在 Object Explorer 结果页直接编辑。一旦用户满足该 inline edit action 的 **submission criteria**，悬停值旁会出现一支笔；点该值会启用可编辑字段（具体取决于属性类型）。提交时**需要再次通过 submission criteria**，否则提交按钮不可选。

**其它（overview 页）**：可**对比对象集**、对对象集执行批量 Actions、把对象集打开到其它兼容应用（如 Quiver）或导出；可**保存 Explorations** 并随时回看最新结果。exploration view 是预设且可配置的可视化集合（如图表、地图），可进一步下钻到具体对象子集。

### 5.3 两者差异（基于文档陈述的归纳）

| 维度 | Vertex | Object Explorer |
| --- | --- | --- |
| **核心对象** | **图（graph）**：节点 = 对象，边 = 链接（或事务对象） | **对象集（object set）**：搜索结果 → 表格 / 预览 |
| **首要目的** | 可视化并量化**因果关系**；监控、模拟、优化运营决策 | 回答关于本体中任何事物的**问题**（搜索与分析） |
| **主要交互原语** | Search Around（含多步、带参数、可保存）、布局、layer 样式、直方图过滤、saved styles/selections、时间 «scrub» | 搜索栏 → 过滤 → 沿链接 pivot → 结果表 / 对象预览 → 批量动作 / 打开到别处 / 导出 |
| **配置模型（文档口径）** | 可访问并使用组织已发布/整理的图，也可自建；图模板是**基于参数生成带定义样式**的可复用资源，可嵌入 Workshop 与 Object View；模板需构建者配置（参数、Search Arounds、layers、布局） | **Walk-up usable**：几乎无需预配置，Ontology 定义好即可用；面向技术背景较弱的用户 |
| **工作流风格（文档口径）** | 文档未在应用对照表中单列 Vertex；其说明强调探索既有图或新建 system graphs，并支持模拟/优化 | **Exploratory**（应用对照表中明确） |
| **与 Workshop 的关系** | 图模板可通过 **Vertex widget** 嵌入 Workshop；模块内的图改动不更新底层模板，样式改动不持久化 | 对象集可打开到 Workshop 等兼容应用 |
| **批量写回** | 文档未描述 Vertex 内的批量动作（其侧重点是探索、模拟、样式与模板） | 明确支持：Actions 分类下按选中对象集批量提交 action；**选中超过 1000 个对象时 Actions 不可用** |
| **时间维度** | 有专门的时间处理：按时间序列着色、**time selection panel** 拖动游标查看动态样式、事件 badge 仅在事件进行中显示、extended labels 可混合真实时间序列读数与模拟值 | 时间序列以**列**形式呈现：最新观测 + sparkline；无时间游标/模拟能力描述 |
| **对象级跳转** | 点节点 → 选择面板（属性、derived properties）；可右键 Search Around | 点 Title 列 → 新页签 object view；勾选/点其它列 → 右侧 Selection Preview；可 Compare objects（两个对象并排） |
| **空间/位置** | 右侧搜索边栏 `+ New Graph`；工作区含画布、左侧 layers/选择面板、右侧 Search Around 页签、底部 branch 类 taskbar 无关 | 首页全局搜索栏 → 搜索页（All/Objects/Object types/Artifacts 页签 + 侧边栏）→ Exploration 右上角 Actions/Open In/Export |
| **入口归属** | Workspace 侧边栏 **Apps → Operational Applications → Vertex** | 文档未在本次文件中说明其入口归属 |

---

## 6. 设计规范

四份文档的分工：**Best practices** = 设计准则与四条核心原则；**Structural guidance** = 属性、关系、命名与访问控制的结构化做法；**Anti-patterns** = 反复出现的错误模式；**Validation** = 如何用真实业务问题与真人/Agent 演练来验证设计。

### 6.1 Best practices（最佳实践）

**开篇定位**：设计良好的 Ontology 为组织创建统一、直观的表示，支持无缝数据集成、跨职能协作与强大分析。

**设计准则清单（8 条，文档称可作为 Ontology 设计的实用检查表）**：

| 准则 | 内容 | 对应的原则 / 反模式 / 结构建议 |
| --- | --- | --- |
| **Model reality, not systems** | Object types 应代表现实世界实体，而不是单个源系统或部门的表示 | 设计原则：Domain-driven design |
| **Curate intentionally** | 每个属性都应有清晰的业务或技术价值 | 结构建议：Normalization and derived properties |
| **Collaborate across teams** | Ontology 设计应让多个部门或团队的干系人参与；孤岛团队是重复的首要原因 | 设计原则：Do not repeat yourself |
| **Keep object types focused** | 每个 object type 应代表一个明确的实体 | 设计原则：Domain-driven design |
| **Choose the right tool** | 人类或 agentic 决策用 action types，自动化转换用 pipelines | 反模式：The Golden Hammer |
| **Use interfaces for abstraction** | 当实体共享共同特征时，用 interfaces 建模该抽象，而不是创建宽而稀疏的 object types | 设计原则：Composition over deep hierarchies |
| **Document your decisions** | 在 Ontology Manager 中记录 object types、properties 与 links | — |
| **Validate against real business questions** | 运行基于任务的分析演练，确认人与 agent 都能浏览 Ontology 并用它支持有后果的决策 | 验证指引：Ontology design: Validation |

**四条核心设计原则（文档明确：来自政府与商业实施的大量现场经验；按优先级排列；冲突时高优先级原则优先）**：

| 优先级 | 原则 | 核心思想 |
| --- | --- | --- |
| 1 | **Domain-driven design** | 建模真实世界，而不是源数据 |
| 2 | **Do not repeat yourself** | 如果同一个东西你建了三次，就重构 |
| 3 | **Open for extension, closed for modification** | 保护核心模型；让构建者能扩展它们 |
| 4 | **Composition over deep hierarchies** | 偏好通过 interfaces 的多重继承；保持可插拔 |

**原则 1：Domain-driven design**
- Objects 应代表语义上有意义的现实世界概念（如 `Patient`、`WorkOrder`、`Vessel`），而不是数据库表、API 响应或电子表格页签。
- Links 应代表真实关系（"this patient visited this facility"），而不是 join key 或外键产物。
- 明确劝诫：被要求「把某个 dataset 本体化（ontologize a dataset）」时，**要抵制把列 1:1 映射为属性就认为工作完成的冲动**；Kitchen Sink 反模式会产出镜像源系统 schema 怪癖而非有用语义的 Ontology。设计良好的 Ontology 应感觉直观；用户或 AI agent 应能无摩擦地浏览它，因为结构与他们对本领域的既有思考方式一致。
- **反模式表现**：object types 镜像源系统表而非领域实体；属性从源列 1:1 映射而无策展；名称来自源系统惯例（`dtLastInspMod`）而非业务语言（`lastInspectionDate`）；对象模型是通过看数据而非理解领域设计的；一个含多个实体的源行被建模为单个 object type。
- **示例**：含 `order_id`、`customer_name`、`customer_email`、`product_sku`、`quantity` 的 CSV **至少描述三个现实世界实体，而不是一个**。✗ 避免 `OrderData`（一个镜像 CSV 的 object type）；✓ 偏好拆成 `Order`（order_id、quantity，links to → Customer、Product）、`Customer`（name、email）、`Product`（sku）三个建模领域的 object types。
- **反模式影响**：模型不直观（用户与 AI agent 无法自然浏览）；与源脆弱耦合（源系统 schema 变化会破坏 Ontology 消费方）；遗漏关系（作为列嵌入的实体无法被独立链接、搜索或推理）；复用差（被某一系统 schema 塑形的 object types 难以被其它团队或用例采纳）。
- **最佳实践**：先识别现实世界实体再看源 schema（与领域干系人一起定义哪些概念重要，一个 dataset 常常描述多个实体）；把身份与观测分开（若一行代表关于某实体的测量或事件，该实体与观测很可能是不同的 object types）；为人类命名（API 名称应直观自明；偏好 `person.children` 而非 `person.linkedChildPersonObjects`，偏好 `equipment.lastInspectionDate` 而非 `equipment.dtLastInspMod`）；先建模领域再映射数据（理解领域 → 设计对象模型 → 把源数据映射进该模型；不要试图看数据并复制其形状）；把非语义类型标记为 hidden（当非语义类型——服务于技术目的而非建模现实领域实体——为特定工作流所必需时，将其标记为隐藏以保持 Ontology 默认视图干净，同时它们仍可被构建者在构建应用时使用）。

**原则 2：Do not repeat yourself（rule of three）**
- 重复的 object types、冗余属性、复制粘贴的工作流既是维护负担，也是**上下文管理问题**——对人与需要推理 Ontology 的 AI agents 都是如此。目标是每个概念有**唯一的规范表示**，每个对该概念的操作有**唯一的规范工作流**。
- **rule of three**：一个实例是巧合，两个是模式，三个就是该重构的时候。
- **反模式表现**：多个 object types 共享同一组属性与相似 links；同一派生属性逻辑或 action 逻辑出现在多个类型中；不同团队为略有不同的目的创建了近乎相同的 object types；存在带细微差异的复制粘贴工作流。
- **示例**：三个团队各自创建了 schema 重叠的客户相关 object types（Sales Customer / Support Customer / Billing Customer）。✓ 偏好一个规范的 `Customer`（name、email、phone + supportTier、billingAccountId 等区分性属性），**或者**若形状确实不同，则用一个 `CustomerBase` interface 由 `SalesLead`、`SupportContact`、`BillingAccount` 实现。
- **反模式影响**：维护负担（改动必须复制到每个副本，漏改会导致副本漂移）；上下文含糊（用户与 AI agent 无法判断几个近乎相同的类型中哪个是规范的）；行为不一致（重复的 action 或派生属性逻辑随时间分叉，产生冲突结果）；开发工作浪费。
- **最佳实践**：审计重复（若多个 object types 共享共同形状——相同属性、相似 links、相似 actions——评估它们是否应是一个带区分属性的单一类型，或应实现一个共享 interface）；合并共享逻辑（若同一派生属性或 action 逻辑出现在多个类型中，抽取进一个 interface 或共享 function）；统一团队特有副本（把不同组创建的近乎相同的 object types 统一为单一规范表示，配以适当的安全或过滤）；应用 rule of three（一个重复可接受，两个是警告信号，三个就该重构）。

**原则 3：Open for extension, closed for modification**
- 一旦某个 object type、interface 或 workflow 经过现场检验并进入生产，其核心结构应保持稳定。组织中其它开发者与团队应能在其上构建——添加实现某 interface 的新 object types、或消费既有对象的新 workflows——**无需修改核心模型**。
- **反模式表现**：对已确立的 object types 频繁做破坏性改动并级联影响依赖应用；新用例需要修改既有核心类型而非扩展它；团队需要编辑共享 interfaces 或 actions 来迁就团队特有需求；为一个团队的扩展做的安全改动意外影响其它消费方。
- **示例**：核心 `Equipment` object type 与 `Inspectable` interface 已投产，新团队需要为部分设备跟踪认证数据。✗ 避免：直接往核心 `Equipment` 加 `certificationAuthority`、`certificationExpiry`、`certificationStatus`、`lastCertAudit` 四个属性（对非认证设备全为 null，既有消费方必须处理变化）。✓ 偏好：核心 `Equipment` 不变，新建链接类型 `Equipment Certification`（含上述四项），并新增 `Certifiable` interface（`certificationStatus`、`certificationExpiry`）——核心类型不动，通过链接类型与 interface 添加新能力。
- **反模式影响**：破坏性改动会打断依赖的 applications、actions 与 workflows；范围蔓延（核心类型为每个新用例积累属性与逻辑，趋向 God Object）；所有权纠缠（多个团队修改同一核心类型，造成合并冲突与责任不清）；安全泄漏（在没有清晰边界的情况下扩展核心类型可能意外扩大数据访问）。
- **最佳实践**：识别什么是本质的（确定哪些属性与 links 对该实体真正基础，把它们锁定）；为扩展而设计（创建核心类型与 interfaces 时预期他人会在其上构建，为链接式扩展类型与新 interface 实现留出空间）；扩展而非修改（往既有模型添加内容时，考虑该添加应属于核心类型，还是属于一个扩展——新链接 object type、新 interface 实现或新属性命名空间）；强制安全边界（核心数据模型应有良好定义的安全边界，使扩展 Ontology 不会意外扩大访问）。

**原则 4：Composition over deep hierarchies**
- Foundry 的 Ontology 通过 interfaces 支持**多重继承**，因此一个实体可以由多个专注的抽象**组合**出行为，而不是单继承链。
- **反模式表现**：很深的单继承链，子类型存在的唯一目的是组合父类型能力；像 `SchedulableBuilding` 或 `InspectableVehicle` 这样把两个不相关概念合并进一个类型的「组合型」类型；workflows 在可以作用于共享 interface 时却紧绑到特定 object types；给实体加一个新能力需要重构继承链。
- **示例**：一个 `Arena` 既需要是 building，又需要是可调度资源。✗ 避免：`Asset → PhysicalAsset → Building → SchedulableBuilding → Arena` 的深单继承（每出现一种新的能力组合就需要新的中间类型；`SchedulableWarehouse` 又要再加一个分支）。✓ 偏好：`Interface: Building`（address、squareFootage）+ `Interface: SchedulableResource`（schedulingCalendar、bookingPolicy）；`Arena` 同时实现两者（arenaName、seatingCapacity）——添加 `SchedulableWarehouse` 只需实现同样的两个 interface，无需新层级。
- **反模式影响**：组合爆炸（每种能力组合都需要新的中间类型）；层级脆弱（父类型改动不可预测地级联到所有后代）；复用受限（建在链深处某个特定类型上的 workflows 无法复用于共享同一能力的其它类型）；语义扭曲（像 `SchedulableBuilding` 这样牵强的父类型不代表现实世界概念，违反 domain-driven design 原则）。
- **最佳实践**：围绕能力或角色设计 interfaces（用 `Inspectable`、`Schedulable`、`Billable`、`Depreciable` 等专注 interface 捕获特定行为或属性集）；用分类学（taxonomic）interfaces 做聚合（如 `MilitaryAsset` 由 `Aircraft`、`Vessel`、`GroundVehicle` 实现，对下钻调查或类似聚合工作流特别有用）；在 workflows 中面向 interfaces（构建 actions、functions 与应用时尽可能面向 interface——建在 `SchedulableResource` 上的工作流无需修改即可用于场馆、会议室与车辆）；组合而非继承（实体需要多种能力时实现多个 interfaces，而不是插入深单继承链）。

**务实与取舍（Pragmatism and tradeoffs）**——文档明确「这些原则是指导，不是法律」：

| 指引 | 详情 |
| --- | --- |
| **在不为难的前提下朝好设计靠** | 若某事物需要在很紧的期限内可用，先构建合理的东西，并留出清晰改进路径 |
| **明确说出取舍** | 建议走捷径时，解释放弃了什么、什么时候会变得重要。例如反规范化在当前规模下没问题，但若增长超过 1 万个对象，你可能想重新审视 |
| **偏好渐进改进而非大爆炸式重构** | 一个略不完美但已在使用并产生价值的 Ontology，优于理论上完美但仍在设计中的 Ontology |
| **捍卫关键不变量** | 命名质量、语义清晰度与安全设计后期很难修复；可以在实现细节上妥协，但不要在这些上妥协 |

文档结论：Ontology 是驱动你组织的软件；用对待生产代码库的同等用心对待它，但**优先业务价值而非完美**。

### 6.2 Structural guidance（结构指引）

**A. Normalization and derived properties（规范化与派生属性）**
- 核心规则：**每个事实只存一次；用 derived properties 获得便利。**
- 风险说明：反规范化数据（把链接对象的值复制到父对象上）有风险——数据源变化时每个副本都必须更新。规范化保持数据一致，而 derived properties 提供反规范化访问的便利且无需维护开销。
- 并非所有计算值都一样，正确做法取决于该值是否能从稳定输入安全地预计算、或是否需要与动态的 Ontology 变化保持同步：

| 类型 | 特征 | 推荐工具 | 示例 |
| --- | --- | --- | --- |
| **Pre-computed** | 由**同一对象上**的属性计算；输入很少变化、或仅因管道摄取而变化 | Pipeline transform | `fullName = firstName + " " + lastName`：输入稳定且在同一条管道中更新，因此预计算是安全的，且不增加运行时开销 |
| **Dynamically derived** | 依赖**链接对象**、或通过 actions、automations 或其它 Ontology 级操作而变化的值 | Derived property | `directReportCount`：员工通过 actions 被重新分配、入职与离职，一个统计链接 `Employee` 对象的 derived property 会自动保持正确 |

- **重要陷阱**：当一个值依赖通过 actions 做出的变化时，**每一个可能影响该值的 action 也都必须更新该值**；若有任何 action 未做到，该值会一直不正确，直到差异被发现。
- **反模式表现**：同一个值作为属性存储在多个 object types 上；属性因为是从别处维护的值的副本而变陈旧；更新单个现实世界事实需要写入多个对象；整数或计数属性被手工维护而不是从 links 计算。
- **示例**：`Manager` object type 需要显示直接下属数量。✗ 避免：`directReportCount: 5`（手工维护的整数，每次员工进出都要更新）；`Employee.managerName: "Alice"`（从链接的 Manager 复制，经理改名就失效）。✓ 偏好：`Manager.directReportCount` 作为**派生属性**，在查询时统计链接的 `Employee` 对象；`Employee.manager` 为指向 Manager 的 **link**。
- **性能考量**：

| 规模 | 建议 |
| --- | --- |
| 低到中等（每查询 < ~1 万个对象） | 自由使用 derived properties；运行时求值对多数工作流足够高效 |
| 高（每查询 > ~1 万个对象） | derived properties 可能因更高开销的查询路径引入延迟。反规范化可能是合适的取舍，但**应是有意识、有记录的决定，而不是默认做法** |

- **最佳实践**：把每个事实存放在一个地方（存在它语义上所属的对象上）；用 derived properties 在查询时从链接对象计算或聚合值（参阅 derived properties reference 了解各聚合的相对性能）；随规模增长监控性能，若 derived properties 在高规模下引入不可接受的延迟，考虑有选择的反规范化；**对任何反规范化做文档记录**，含理由、事实来源与保持副本同步的更新策略。

**B. Structs（结构体）**
- 核心规则：**把语义相关的字段分组成 structs。**
- 当某个属性天然是多字段的（例如含 street、city、state、postal code 的地址），应使用 struct 而不是扁平化为多个属性；structs 保留语义分组并支持更丰富的元数据捕获。
- **使用场景**：

| 场景 | 示例 |
| --- | --- |
| 多字段值 | 地址（street、city、state、postal code）、坐标（geopoint、altitude） |
| 带元数据的值 | AI 生成输出，含置信度分数、来源引用与推理过程 |
| 带选择逻辑的多值属性 | 多个电话号码，用 reducer 呈现主号码 |

- **示例**：在 `Facility` object type 上建模地址。✗ 避免十个不相关属性（addressStreet、addressCity、addressState、addressPostalCode、addressCountry、addressGeopoint、addressLastOccupied、addressDatasource、addressLlmConfidence、addressLlmReasoning），它们之间唯一的联系是命名约定。✓ 偏好一个 `address (struct array)`，含 street/city/state/postalCode/country（**Main field**）、geopoint、lastOccupied（用于 reducer 排序）、datasource、llmConfidence、llmReasoning——一个语义概念，带主干字段与结构化子字段。
- **主要收益**：
  - **语义分组**：地址是一个概念，而不是十个不相关属性，Ontology 反映这一点；
  - **元数据捕获**：structs 可在主值之外携带来源、置信度与时间戳信息；
  - **Reducer 支持**：在多值场景中，reducers 可呈现出最相关的值（例如 `lastOccupied` 最新的地址）；
  - **Main field 行为**：一个 struct 可以指定一个或多个 **main fields**，使其在 interfaces 与查询中表现得像一个简单属性、或像一个只含子集字段的 struct。
- **文档强调**：structs 在 **AI-first workflows** 中尤其有价值——LLM 输出既有主要结果，也有关联元数据（推理、来源引用、置信度分数）；应把它们一起捕获，而不是散落在不相关属性中。
- **最佳实践**：识别字段语义相关且总是一起使用的多字段属性；用清晰的字段名与类型定义 struct；指定一个 main field 使 struct 在多数情境中表现得像简单属性；对多值 struct 属性使用 reducers 呈现最相关的值；把元数据（来源、置信度、时间戳）与主值一起捕获在 struct 中，对 AI 生成输出尤其如此。

**C. Interfaces（接口）**
- 核心规则：**用 interfaces 构建可复用、面向未来的抽象。** Interfaces 是实现 "Do not repeat yourself" 原则与开闭式（open/closed）可扩展性的主要工具。
- 它们定义一个共享形状（properties、links、actions），多个 object types 可实现，从而使 workflows 可以面向 interface 而不是单个类型。
- **使用场景**：

| 场景 | 示例 |
| --- | --- |
| 跨类型的共同属性 | `Inspectable` interface 含 `lastInspectionDate` 与 `inspectionStatus`，由 `Vehicle`、`Equipment`、`Facility` 实现 |
| 共享工作流 | 面向 `SchedulableResource` 的调度工作流无需修改即可用于场馆、会议室与车辆 |
| 分类学分组 | `MilitaryAsset` interface 由 `Aircraft`、`Vessel`、`GroundVehicle` 实现，用于下钻聚合工作流 |
| 多级抽象 | `SchedulableResource` 扩展 `Trackable`，在更广的跟踪抽象之上增加调度特有属性 |

- **示例**：多个 object types 需要检查跟踪。✗ 避免：`Vehicle`、`Equipment`、`Facility` 各自重复 `lastInspectionDate`、`inspectionStatus`，并各自带一个重复的 action（Schedule Vehicle/Equipment/Facility Inspection）——同一属性与逻辑的三份副本，各自独立维护。✓ 偏好：一个 `Inspectable` interface（含这两个属性 + 一个共享 action `Schedule Inspection`），`Vehicle`（make、model、mileage…）、`Equipment`（serialNumber、warrantyExpiry…）、`Facility`（address、capacity…）分别实现它——一个 interface、一个共享 action、三个实现类型。
- **平台考量（重要）**：

| 情况 | 指引 |
| --- | --- |
| 该 interface 在你的工作流中已被完整支持 | 直接面向 interface；单个工作流覆盖所有实现类型 |
| 该 interface 在某个特定情境中尚未被支持 | **现在就定义该 interface**，并按类型复制工作流作为临时手段。文档说明这种做法**不比没有 interface 时更低效**，且一旦支持到位就有清晰的合并路径 |

- **最佳实践**：识别共同形状（多个 object types 共享属性、links 或 actions 时，定义捕获该共享形状的 interface）；围绕能力或分类学设计 interfaces（能力型如 `Inspectable`、`Schedulable`、`Billable`；分类学型如 `MilitaryAsset`、`MedicalDevice`）；在 workflows 中面向 interfaces（尽可能针对 interfaces 构建 actions、functions 与应用）；扩展 interfaces 以实现多级抽象（interfaces 可以扩展其它 interfaces 以构建分层抽象）；先搭脚手架、后续再合并（即使因当前平台支持缺口而必须临时按类型复制工作流，也要定义 interfaces）。

**D. Links and object-backed link types（链接与对象支撑的链接类型）**
- 核心规则：**Links 应代表语义上有意义的关系。** 每个 link type 都应回答一个清晰的领域问题，例如：该病人访问了哪个机构？该员工属于哪个团队？该工单使用了哪些设备？
- **何时使用哪种**：

| Link type | 使用时机 | 示例 |
| --- | --- | --- |
| **Direct link** | 关系有意义但自身不携带元数据 | `Employee → Department` |
| **Object-backed link** | 关系携带自身元数据（日期、角色、状态、分配比例） | `Employee → VentureStaffing → Venture`（带 role、startDate、allocation） |

- 文档补充：**并非每个链接对象都需要在每个情境中可见**。有些工作流关心 join 元数据，有些只想要直接连接。object-backed links 让你能按工作流暴露任一视图。
- **示例**：建模员工与 venture 之间的关系，每次分配都有角色与开始日期。✗ 避免：`Employee → Venture` 直接链接（无法捕获每次分配的 role、start date 或 allocation）；或在 `Employee` 上放 `ventureRole`、`ventureStartDate`（当员工有多个 venture 分配时语义含糊）。✓ 偏好：`Employee → Venture Staffing → Venture`，`Venture Staffing` 含 role、startDate、allocationPercentage、status；工作流可暴露两种视图——**直接**：Employee → Venture；**详细**：Employee → Staffing → Venture。
- **错误链接设计的影响**：丢失元数据（直接链接无法捕获关系存在的时间、原因或身份/角色）；多链接含糊（当实体参与多个关系时，源对象上的 `ventureRole` 这类属性变得有歧义）；无意义链接（仅因两个 datasets 共享外键而存在的 links 会给 Ontology 增加噪声并困扰导航）。
- **最佳实践**：验证语义意义（避免仅因两个 datasets 共享外键而存在的 links；问该关系在领域中有意义吗）；评估关系是否携带元数据（若有日期、角色、状态，用 object-backed link type 捕获）；暴露合适的细节层级（按情境设计工作流使用直接关系或经链接对象的详细关系）；为清晰命名 links（link 名称应描述从各方向看的关系含义）。

**E. Naming conventions（命名约定）**
- 核心规则：**为人类可读性与 agent 可导航性优化。** 一致、描述性的命名是你能在 Ontology 质量上做的最有影响力的投入之一；清晰的名称让 Ontology 更容易被人与 AI agent 浏览，且一旦 Ontology 在使用中就更难纠正。
- **命名规则表**：

| 元素 | 约定 | 好例子 | 坏例子 |
| --- | --- | --- | --- |
| **Object types** | 领域专家能认出的**单数具体名词** | `Patient`、`WorkOrder`、`FlightSegment` | `Data`、`Item`、`Record` |
| **Properties** | 简洁、自明；**不编码类型信息或实现细节** | `age`、`status`、`lastInspectionDate` | `dtLastInspMod`、`nVAL01`、`fieldX` |
| **Links** | 从**每个方向**读起来都自然 | `department`（Employee → Dept）、`employees`（Dept → Employee） | `relatedItems`、`link1` |
| **Dates** | 在整个 Ontology 中**一致遵循单一约定** | `createdDate`、`updatedDate`、`effectiveDate` | 混用 `createdDate` 与 `dateOfCreation` |
| **Ambiguous terms** | 用具体含义限定 | `monetaryValue`、`quantityOnHand`、`riskScore` | `value`、`quantity`、`score` |

- **示例**：`Item` → `Product`；`dtLastInspMod` → `lastInspectionDate`；`value` → `monetaryValue`；`Item → Related Item` → `Product → Supplier`、`Employee → Supervisor`。
- **最佳实践**：在构建前建立命名约定（就日期、状态、标识符与 links 的模式达成一致）；遵循 Ontology 中已确立的约定（若 Ontology 已用 `createdDate`，不要引入 `dateOfCreation`）；限定含糊属性（用 `monetaryValue`、`quantityOnHand`、`riskScore`，不要用 `value`、`quantity`、`score`）；按关系命名 links（从 `Employee` 到 `Department` 的 link 从员工视角是 `department`，从部门视角是 `employees`）；与终端用户一起审查名称（对构建者来说清晰的名称对消费者可能含糊；用 analytical drills 观察用户搜索的术语与他们期望找到的关系）。

**F. Security design（安全设计）**
- 核心规则：**按语义设计安全，遵循最小权限（least privilege）原则。** Ontology 中的安全应以**领域中有意义的术语**表达，而不是以数据基础设施的术语表达；用户应能看着一份安全配置就理解什么被保护、为什么。
- **安全模型：结合行级与列级安全，实现细粒度的单元格级访问控制**：

| 安全层 | 控制什么 | 示例 |
| --- | --- | --- |
| **Row-level** | 用户能查看哪些对象 | VIP 患者仅限高级人员 |
| **Column-level** | 用户在可见对象上能查看哪些属性 | 临床记录仅限护理团队 |
| **Cell-level（组合）** | 行与列限制的交集 | VIP 患者的临床记录仅对高级护理团队可见 |

- **示例**：控制对敏感患者数据的访问。✗ 避免：拆成 `PublicPatient`（name、dob、diagnosis）与 `RestrictedPatient`（name、dob、diagnosis、clinicalNotes、mentalHealthRecords）两个 object types——schema 重复，靠拆分类型实现安全；给一个类型加的属性容易在另一个上被遗忘。✓ 偏好：一个 `Patient` object type，`diagnosis`/`clinicalNotes`/`mentalHealthRecords` 做**列级限制**（分别限护理团队、精神科团队），**行级安全**限制 VIP 患者仅限高级人员——一个类型，靠 policy 实现安全，领域边界驱动访问规则。
- **错误安全设计的影响**：为安全而重复类型（schema 漂移，给一个类型加的属性容易在另一个上被遗忘，违反 "Do not repeat yourself"）；默认过于宽松（先给宽访问再收紧，会在锁定完成前暴露敏感数据）；用临时过滤代替 policy（安全逻辑散落在应用代码中而不是在 Ontology 层强制执行，脆弱且难以审计）；边界错位（不遵循领域边界的安全边界更难推理，也更可能有缺口）。
- **最佳实践**：**从限制性开始、有意识地放开**（默认最小访问、按需放宽，而不是先放开再限制）；**同时使用行级与列级安全**以实现细粒度的单元格级访问控制；**让安全与领域边界对齐**（若领域有天然的访问边界——区域经理看本区域数据、护理团队看自己的患者——用 Ontology 关系与安全策略建模这些边界，而不是临时数据过滤）；**不要为安全而重复 object types**（一个有良好设计安全策略的单一类型优于多个 schema 重复的类型）；**审查新增本体路径的访问控制一致性**（确保新增的 links、types 或 properties 保持对受限数据的既定保护）。
- 文档补充：访问控制回答**谁可以使用数据**，而隐私与公民自由（privacy and civil liberties）规划还问**为什么**某工作流需要该数据、是否更少的数据也能达到目的。

### 6.3 Anti-patterns（反模式）——逐条列出

**总表（8 条，原文表格）**：

| Anti-pattern | Description | Solution |
| --- | --- | --- |
| **System Silos** | 为每个来源系统创建独立的 object types | 在 pipelines 中合并数据；创建统一的 object types |
| **The Kitchen Sink** | 把不必要的技术列作为属性纳入 | 有意图地策展属性；排除 ETL 元数据 |
| **Department Silos** | 每个部门各自创建共享实体的自己版本 | 创建共享 object types；部门特有数据用属性与 links 表达 |
| **The God Object** | 一个 object type 代表多个不同实体 | 创建不同的 object types；共享特征用 interfaces |
| **The Golden Hammer** | 过度依赖单一工具（例如 action types、pipelines 或 functions）解决所有问题，而不是选择正确的能力 | 让工具匹配工作：数据加工用批量或流式 pipelines、人类决策用 actions、事件驱动反应用 automations、复杂实时逻辑用 functions |
| **Action Sprawl** | 创建大量单属性 action 而不是内聚的业务操作 | 围绕业务操作设计 actions，把相关改动打包成有意义的工作流 |
| **The Time Machine** | 把历史版本建模为独立对象或 object types | 每个实体用单个对象 + 链接的历史/修正（amendment）对象与时间序列属性 |
| **The Misnomer** | 对 Ontology 元素使用含糊、通用或误导性的名称 | 使用具体、描述性的名称；限定含糊属性；按关系命名 links |

**文档开篇说明**：即使经验丰富的 Ontology 设计者也常落入看似合理、但随着 Ontology 增长会造成重大问题的常见设计陷阱。避免这些反模式有助于构建准确代表业务领域、减少维护开销、并支持强大跨职能工作流的 Ontology。

以下逐条展开（只列文档写明的要点）：

---

**反模式 1：System Silos（系统孤岛）**
- **定义**：当你**依据数据来自哪个源系统**、而不是依据实体本身来建模，从而为同一个现实世界实体创建多个独立 object types 时发生。
- **常见成因**：不同团队拥有不同源系统并各自独立构建；不确定如何合并多来源数据；希望保留系统特有字段而不决定哪些是本质的。
- **示例**：员工数据在三个系统中——HR 系统、门禁系统、项目管理工具。不是创建一个 `Employee` object type，而是创建 `HR System Employee`、`Badge System Employee`、`Project Management Employee`。
- **问题与影响**：
  - 碎片化的现实视图：终端用户看不到员工的统一视图，必须在多个 object types 间穿梭才能理解全貌；
  - 重复投入：对概念上同一个实体，action types、link types 与应用必须建多遍；
  - 数据不一致：同一员工在不同 object types 中可能有冲突信息，且没有清晰的事实来源；
  - 维护复杂：业务逻辑的改动必须在所有系统特有 object types 上复制。
- **解决方案**：创建一个代表现实世界实体的单一 object type，并用数据管道把多个源系统的信息合并进**统一的 backing dataset**。
- **实施步骤**：① 找出跨系统唯一标识该实体的主键（例如 employee ID）；② 构建 join 所有源系统数据的 transform；③ 为冲突值定义清晰的优先级规则（例如 HR 系统对 job title 具有权威性）；④ 创建由合并后 dataset 支撑的单一 object type。

---

**反模式 2：The Kitchen Sink（什么都往里塞）**
- **定义**（也称 "everything but the kitchen sink"）：object types 包含来自外部系统的、在 Ontology 语境中没有业务相关性的不必要列，用技术性产物把数据模型塞满。
- **常见成因**：「以防万一」心态（保留以后可能有用的字段）；不清楚哪些字段有意义；从源系统直接映射而不策展；害怕因排除列而丢失数据。
- **示例**：从 CRM 系统集成创建 `Customer` object type 时纳入所有可用列——保留 `customer_id`、`customer_name`、`email`；不保留 `_crm_extracted_at`、`_crm_received_at`、`_crm_batched_at`、`_crm_sequence`、`_crm_table_version`、`_crm_internal_record_id`、`last_etl_update_timestamp`。
- **问题与影响**：混淆（终端用户在业务数据旁看到无关技术字段）；性能下降（不必要的属性增加数据规模、计算、索引大小，并拖慢搜索）；洞见被掩盖（重要业务属性淹没在系统元数据中）。
- **解决方案**：有意图地策展属性。只纳入有清晰业务含义、且对工作流有用的列。
- **纳入 vs 排除指引**：

| Include（纳入） | Exclude（排除） |
| --- | --- |
| 业务标识符（customer ID、order number） | 管道元数据 |
| 人类可读属性（name、description） | 无业务含义的内部系统 ID |
| 与业务流程相关的日期 | 只对数据工程有意义的时间戳 |
| 用于过滤或 actions 的状态字段 | 用于管道调试的审计列 |

- **实施步骤**：① 逐个列问「有没有人会需要看到、搜索或按它过滤？」；② 把技术元数据留在 backing dataset 中用于调试，但不要作为属性暴露；③ 用属性可见性设置隐藏那些必须存在但很少需要的边界属性；④ 记录每个属性为何存在、谁使用它。

---

**反模式 3：Department Silos（部门孤岛）**
- **定义**：不同部门创建同一个 object type 的各自版本，导致 Ontology 反映的是组织结构而不是业务现实。
- **常见成因**：部门孤立工作，缺少跨职能协调；每个团队认为自己对客户的看法是独特的；缺少治理或中心化的 Ontology 设计权威；团队想要自治并控制「自己的」数据。
- **示例**：多个部门需要处理客户数据，各自创建自己的 object type——销售团队建 `Sales Customer`，支持团队建 `Support Customer`，财务团队建 `Billing Customer`，市场团队建 `Marketing Contact`。四个 object types 代表同一个现实世界实体：客户。
- **问题与影响**：没有单一事实来源（不同部门对同一客户有冲突信息）；无法做跨职能工作流（难以回答「给我看这个客户在销售、支持与账务上的所有交互」）；重复开发（每个部门构建冗余的 actions、links 与应用）；治理噩梦（数据质量问题倍增；在一个 object type 中的修复不会传播到其它）。
- **解决方案**：创建服务多个部门的共享 object types，需要时用属性与 links 捕获部门特有信息。
- **实施步骤**：① 找出跨部门边界存在的实体；② 建立跨职能工作组来定义共享 object types；③ 用属性在共享对象上捕获部门特有属性；④ 用 link types 把共享对象连接到部门特有对象（如 `Customer → Support Ticket`）；⑤ 若部门需要同一底层实体的不同「视图」，使用 object views 或策展的 Workshop 与 OSDK 应用；⑥ 若某些属性只能被特定团队访问，使用 **restricted views**。

---

**反模式 4：The God Object（上帝对象）**
- **定义**：单个 object type 被过度负载，代表多个不同的现实世界实体，导致一个臃肿、混乱、无法维护的 object type。
- **常见成因**：由表面相似性驱动的过度抽象（「它们都是资产」）；希望最小化 object types 数量；构建前缺少清晰的实体定义；随着更多用例加入既有 object type 而范围蔓延。
- **判断指标（indicators）**：object type 有很多经常为 null 的属性；属性含义随另一个属性值（如 type 或 category）而变；查看对象时你会问自己「这是什么种类的 `[Object]`？」；业务规则与校验需要基于对象「type」的大量条件逻辑。
- **示例**：你创建一个意在代表「任何有价值之物」的 `Asset` object type，最终包含物理设备（卡车、机械）、软件许可、房地产、金融工具、员工（作为「人力资产」）。该 object type 有 **150+ 属性**，对任一给定对象大多为 null，而 `value`、`location`、`status` 等属性的含义完全取决于这个「资产」代表什么种类。
- **问题与影响**：语义混乱（终端用户无法理解 `Asset` 究竟代表什么）；数据稀疏（多数对象的多数属性为 null，数据难以解读）；无法校验（无法强制业务规则，因为规则随实体类型不同）；搜索体验差（搜 `Assets` 返回互不相关之物的混合）；action type 复杂度（actions 必须以复杂条件逻辑处理迥然不同的实体类型）。
- **解决方案**：为不同的现实世界实体创建不同的 object types。当实体**确实**共享共同属性或行为时，用 interfaces 建模共享特征。
- **实施步骤**：① 列出当前由该 object type 代表的不同现实世界实体；② 为每个不同实体创建独立 object types；③ 识别真正共享的属性与行为；④ 用 interfaces 跨 object types 建模共享特征；⑤ 把既有对象迁移到合适的新 object types。（原文图中示例方向：`Asset`（assetType、assetSubtype、value、location、status + 145 个属性）→ `Equipment` / `Vehicle` / `Software License` / `Property (Real Estate)` / `Financial Instrument`，并抽象出 `Interface: Depreciable Asset`（purchaseDate、purchaseValue、depreciationSchedule）。）

---

**反模式 5：The Golden Hammer（金锤子）**
- **定义**：过度依赖单一工具解决每个问题，即使其它方式更合适。名字来自谚语「如果你只有一把锤子，一切看起来都像钉子」。表现：在本更适合 pipelines 的工作中滥用 action types；为应由事件驱动 automations 处理的逻辑构建 pipelines；为更适合在 transform 中预计算的运算编写 functions。
- **常见成因**：因熟悉度与团队内可见性而过度依赖某工具；想让终端用户「控制」计算何时发生；对完整平台（pipelines、automations、functions、scheduled builds）不熟悉；只从单一层思考（Ontology-first、pipeline-first 或 code-first）而不考虑完整工具集。
- **示例**：
  - **过度依赖 action types**：需要为展示按区域总销售额的看板计算聚合指标。不是用数据管道预计算这些指标，而是创建一个名为 `Calculate Regional Sales Totals` 的 action type，要求终端用户手工触发，结果通过该 action 写回对象。
  - **过度依赖 pipelines**：当传感器读数超过阈值时由管道创建一个告警对象。你想自动把该告警分配给值班工程师并发送通知。不是用对**新对象**做出反应的 automation，而是构建额外的管道逻辑试图解析被指派人并把分配写进 backing dataset，把运营工作流逻辑混进数据集成。
  - **过度依赖 functions**：把简单属性派生 `fullName = firstName + lastName` 实现为 function-backed column，增加了运行时开销与一个需要维护的 code repository，而一条管道的 `concat` 表达式就够了。
- **问题与影响**：可扩展性限制（每个工具有不同的执行限制，用错工具会提前撞到天花板）；不必要的复杂度（在错误的层维护逻辑会增加活动部件）；用户负担（终端用户必须执行平台本可自动完成的步骤）；性能问题（通过 actions 或 functions 做实时计算比预计算的管道结果更慢；反之，调度管道对事件驱动反应来说太慢）；调试困难（逻辑在错误的层时，失败更难诊断与解决）。
- **解决方案**：按用例选择正确工具。**原文对照表**：

| 工具 | 最适合 | 不适合 |
| --- | --- | --- |
| **Action types** | 人类决策、用户发起的一个或少数对象的编辑、应立即生效的输入驱动改动 | 批量计算、调度更新、无人参与的事件驱动反应 |
| **Pipelines (batch)** | 批量数据处理、聚合、清洗、富化、按计划或在数据到达时预计算派生值 | 对单个对象变化的实时反应、需要人类输入的逻辑 |
| **Pipelines (streaming)** | 连续、低延迟的数据处理，结果须随源数据到达而保持最新（实时看板、实时状态跟踪、持续富化） | 批量已足够的不频繁更新、需要人类输入的逻辑、对 Ontology 级事件做出反应（用 automations） |
| **Automations** | 对 Ontology 变化（对象创建、属性更新、调度触发）的事件驱动反应，在无用户参与下编排 actions 或通知 | 重数据加工、复杂的多 dataset join、需要人类判断的逻辑 |
| **Functions** | 跨多个对象的复杂实时计算、校验逻辑、依赖实时 Ontology 状态且无法预计算的派生值 | 可在管道中计算的简单派生、大批量数据集的批处理 |
| **Schedules** | 周期性管道构建、基于时间或事件的数据刷新编排 | 实时对单个对象级变化做出反应 |

- **应用该指引的示例（原文对照）**：
  - ✗ `Action: "Calculate Regional Sales"` → ✓ 每天把销售数据聚合进一个 `Regional Sales Summary` object type 的管道；
  - ✗ `Action: "Standardize Address Format"` → ✓ 在摄取时清洗地址的管道；
  - ✗ `Action: "Update Inventory Status"`（基于数量阈值）→ ✓ 每次同步时按数量阈值设置状态的管道；
  - ✗ `Action: "Assign Risk Score"`（用公式）→ ✓ 计算风险分并写入 backing dataset 的管道或模型；
  - ✗ 通过写入 backing dataset 把告警分配给值班工程师的管道 → ✓ 当新 `Alert` 对象被创建时触发「Assign Alert」action 的 automation；
  - ✗ 某对象满足条件时发送通知的管道 → ✓ 监控该条件并发送通知或触发 action 的 automation；
  - ✗ 每分钟轮询新 IoT 传感器读数的批量管道 → ✓ 随传感器数据到达而持续处理的流式管道；
  - ✗ `fullName = firstName + " " + lastName` 的 function-backed column → ✓ 在 backing dataset 中计算 `fullName` 的管道；
  - ✗ 每分钟运行以检查需跟进对象的调度管道 → ✓ 对特定对象变化做出反应并立即触发跟进的 automation。
- **实施步骤（原文「动手前先问」）**：
  - **创建 action type 之前**问：「这需要人类判断或用户输入吗？」若不需要，它很可能属于管道或 automation。
  - **把逻辑加进管道之前**问：「这是数据转换，还是运营工作流？」数据清洗、聚合与富化属于管道；分配工作、发送通知、对单个变化做出反应属于 automations。
  - **写 function 之前**问：「这能在 backing pipeline 中预计算吗？」若结果只依赖源数据列且不需要实时 Ontology 遍历，就在上游计算。
  - **构建轮询管道之前**（每 N 分钟运行以检测变化）问：「automation 能直接对该事件做出反应吗？」Automations 以近实时响应 Ontology 变化，没有调度构建的开销；若需求是对源系统的持续数据处理，考虑流式管道。
  - **默认采用批量管道之前**问：「这些数据需要持续保持最新吗？」若消费方依赖低延迟的新鲜度，流式管道可避免批量调度的妥协。
  - **用 automations** 弥合「某事发生了变化」与「某事应该发生」之间的空隙，而不需要用户按钮点击或轮询管道。

---

**反模式 6：Action Sprawl（动作泛滥）**
- **定义**：创建许多范围狭窄、各自只修改单个属性的 action types，而不是设计代表有意义业务操作的内聚 actions。
- **常见成因**：把 actions 想成数据库列更新而不是业务操作；增量式构建 actions 而不考虑整体用户体验；不了解 actions 如何打包多个属性改动；模仿传统应用开发中的 CRUD 操作。
- **判断指标**：单个 object type 有**超过 10 个** action types；多个 actions 总是按顺序执行；action 名称读起来像 `Set [Property]` 或 `Update [Property]`；终端用户抱怨完成任务步骤太多。
- **示例**：对 `Employee` object type，不是创建有意义的业务 actions，而是创建 `Update Employee First Name`、`Update Employee Last Name`、`Update Employee Email`、`Update Employee Phone`、`Update Employee Department`、`Update Employee Manager`……以及另外 20 多个单属性 actions。
- **问题与影响**：体验压倒（终端用户面对冗长杂乱的 actions 列表，难以找到对的那个）；工作流碎片化（简单更新需要多次 action 提交才能完成一个业务任务）；缺少内聚的业务表示（actions 不映射现实流程，Ontology 不直观）；审计线索碎片化（改动历史散落在许多小 actions 中，难以理解发生了什么与为什么）。
- **解决方案**：围绕**业务操作**而不是数据库更新设计 action types。创建把相关改动打包成有意义工作流的 actions。
- **实施步骤**：① 梳理涉及改动对象数据的真实业务流程；② 把相关属性改动分组为代表这些流程的单个 actions；③ 用 action 参数在一个内聚 action 内允许可选字段；④ 用业务操作命名 actions——`Transfer Employee`、`Approve Purchase Order`、`Escalate Support Ticket`；⑤ 用 action rules 与校验逻辑在 action 内强制业务约束。（原文对照方向：六个 `Update Employee X` / `Update Employee Department`+`Update Employee Manager` / `Create Employee Record`+`Set Employee Start Date`+`Assign Employee Badge`+`Assign Employee Equipment` → `Update Employee Contact Information`（firstName/lastName/email/phone）、`Transfer Employee to New Department`（newDepartment/newManager/newLocation/effectiveDate）、`Onboard New Employee`（新员工所有必填字段 + 触发下游工作流如工牌分配、设备申请）。）

---

**反模式 7：The Time Machine（时间机器）**
- **定义**：把实体的历史版本建模为独立对象或 object types，而不是使用时间序列数据、快照或恰当的版本策略。
- **常见成因**：希望保留每次变化的完整历史；误解如何在 Ontology 中建模时间性数据；把文件版本化心智模型（v1、v2、v3）套到对象设计上；不了解时间序列属性或链接式历史模式。
- **判断指标**：object type 包含多个代表同一现实世界实体在不同时间点的对象；存在 `version`、`revision` 或 `isCurrent` 之类属性用于区分副本；对象数量随**变化次数**成比例增长，而不是随**实体数量**增长；终端用户困惑该引用或链接哪个对象。
- **示例**：为跟踪 `Contract` 的变化，创建 `Contract v1`、`Contract v2`、`Contract v3` 作为同一 object type 下的独立对象；**更糟的是**把 `Contract 2023`、`Contract 2024`、`Contract 2025` 作为每年一个独立 object type。每个「版本」都是合同的完整副本，属性值略有不同，而指向其它对象（如 `Vendor` 或 `Department`）的链接在所有版本上重复。
- **问题与影响**：对象数量爆炸（每次变化都创建新对象，迅速用冗余数据膨胀 Ontology）；当前状态含糊（难以识别哪个版本是「当前」或权威版本）；链接含糊（指向合同的链接变得不清楚，`Vendor` 或 `Department` 该链接哪个版本？）；报表复杂（跨时间段报表需要易错的过滤与去重逻辑）。
- **解决方案**：**每个实体用一个对象**并以其属性表示当前状态。把历史变化存储在单独的链接 object type 中、启用 edits history、或利用时间序列属性。
- **实施步骤**：① 每个现实世界实体使用单一对象，属性反映当前状态；② 创建单独的链接 object type（如 `Contract Amendment` 或 `Contract History`）捕获历史变化；③ 对频繁变化且需要时间性跟踪的值利用时间序列属性；④ 如果需要审计线索，用 backing dataset 或 edits history 维护完整历史记录。（原文对照方向：`Contract v1/v2/v3` 对象，或 `Contract 2023/2024/2025` 逐年 object type → 单个 `Contract` 对象（currentValue、currentStatus、effectiveDate），并 Links to → `Contract Amendments`（amendmentDate、previousValue、newValue、changeReason）。）

---

**反模式 8：The Misnomer（命名错误）**
- **定义**：对 object types、properties 与 link types 使用含糊、通用或误导性的名称，不能清晰传达其含义，导致整个 Ontology 中的混淆与误解。
- **常见成因**：使用对你来说讲得通、对别人不讲得通的简写；名称从源系统列名直接照搬而未翻译；为简洁牺牲清晰；缺少命名约定或治理标准；假定上下文会让含义显而易见。
- **判断指标**：终端用户频繁问「这个属性是什么意思？」或「这是什么种类的 `[Object]`？」；同一个名称可以合理地指多个不同概念；属性名是单个通用词如 `value`、`type`、`status`、`date`、`name` 而无限定；link types 使用「related to」这类通用标签而不指明关系性质。
- **示例**：object type `Item`（什么 item？产品？行项？库存项？）；属性 `value`（货币价值？数量？分数？评级？）；属性 `type`（什么的 type？有效值是什么？）；属性 `date`（创建日期？修改日期？到期日？生效日？）；link type `Item → Related Item`（它们如何相关？父子？替代品？配件？）。遇到这些名称的终端用户必须猜测其含义，或深挖文档才能理解数据实际代表什么。
- **问题与影响**：误解（终端用户没有额外上下文就无法理解 Ontology，导致错误的分析与决策）；陡峭的学习曲线；文档依赖（文档变得必需而非补充，并且很快过时）；跨团队混淆（不同团队对同一含糊名称有不同理解，导致使用不一致）。
- **解决方案**：对所有 Ontology 元素使用具体、描述性的名称。名称应自文档化，使任何人都能在没有额外上下文的情况下理解其含义。
- **实施步骤**：① 在构建前建立命名约定，并通过治理审查强制执行；② 使用具体、描述性的名称：`Product`、`Sales Order Line Item`、`Warehouse Inventory Record`；③ 限定含糊属性：`monetaryValue`、`quantityOnHand`、`riskScore`；④ 按关系命名 links，说明关系含义：`Purchasing Customers`、`Manufacturing Facility`、`Supervisor`；⑤ 为所有 Ontology 元素添加描述，解释其含义与有效值；⑥ 与终端用户一起审查名称，确保其直观且无歧义。（原文对照方向：`Item`→`Product`/`Sales Order Line Item`/`Warehouse Inventory Record`；`value`→`monetaryValue`/`quantityOnHand`/`riskScore`；`type`→`productCategory`/`serviceTier`；`date`→`orderPlacedDate`/`contractEffectiveDate`；`Item → Related Item`→`Product → Purchasing Customer`/`Employee → Supervisor`/`Equipment → Manufacturing Facility`。）

---

**收尾（原文）**：这些反模式常见但可避免。聚焦根本最佳实践——**建模现实而非系统、有意图地策展属性、跨团队协作、为每项任务选择正确工具**——就能构建随组织需求扩展的 Ontology。**有效的 Ontology 设计是迭代的**：从清晰的实体定义开始，尽早让干系人参与，并随着你对什么有效的了解不断精炼模型。遇到挑战时回到本指南的原则，判断是否正在出现某个反模式，并在它变得难以更改之前纠正方向。**用真实业务问题作为验收测试**，确认补救措施让 Ontology 对人**和 agent** 都更易使用。

### 6.4 Design validation（设计验证）

**核心命题**：结构审查能确认 Ontology 语义连贯、技术上正确，但**不能确认有任何人能用它**。基于任务的验证（task-based validation）填补这个缺口：用**将要依赖它的人与 agents**，针对该模型必须支持的决策与调查来测试模型。

**Palantir 的内部做法（原文）**：Palantir 内部使用 **analytical drills（分析演练）**来同时测试 Ontology 设计与流畅度。团队拿到他们**没见过的**业务问题，从简单计数到多步调查不等。参与者使用**通用分析应用**，**不使用**团队为该任务构建的工作流或看板——这个约束测试的是 **Ontology 本身**，而不是应用特有的拐杖。

**从这些演练得到的五条教训（原文表）**：

| 教训 | 覆盖章节 |
| --- | --- |
| 结构正确并不保证运营可用性 | Limits of structural review |
| 真实业务问题是最好的验收测试 | Sourcing real business questions |
| 新用户提供关键证据 | Drill design decisions |
| 回答耗时是一个设计信号 | Reading the results |
| 人与 agent 暴露不同的弱点 | Comparing people and agents |

**A. 结构审查的限度（Limits of structural review）**
- 结构指引能判断某个 object type 是否代表连贯实体、某条 link 是否有意义的多重性、多个类型是否应共享 interface。这些审查必不可少：它们评估模型的内部完整性，防止那些一旦做出就很难逆转的设计选择。
- 但它们**无法**评估「只带着一个业务问题去接近 Ontology」这一体验。该体验不从 schema 图开始，而从**运营状况**开始：产出下降、货物迟到、库存丢失、或延误使排定工作面临风险。从那里用户必须把该状况翻译成 Ontology 的语言，找到一个有用的起始 object type，并沿着符合他们理解组织方式的 links 前进。
- 在每一步，模型要么承载上下文，要么把负担转回用户：含糊的 object type 迫使猜测；没有别名，用户无法按熟悉的名称找到 object type；反映源系统 join 而非真实关系的 link 会打断调查；当两个概念重复时，用户必须已经知道哪个表示是权威的。
- **构建者往往凭记忆就能绕过这些弱点，但仅靠构建者无法验证设计**：使路径显而易见的上下文来自构建者，而不是 Ontology。

**B. 从哪里取材真实业务问题（Sourcing real business questions）**
- 同样的局限也适用于问题本身：若构建者检视既有 Ontology 并问它能回答什么，他们验证的是**自己已知具备**的覆盖；这种做法会系统性地排除那些从未进入设计的概念与关系。
- 应当从组织的**运营节奏（operating rhythm）**中派生问题：
  - 领导者反复问团队什么？
  - 团队在能做出决定之前需要彼此提供什么？
  - 哪项调查依赖某个知道每条信息在哪里的资深人员？
  - 哪份周期报表之所以存在，是因为底层答案否则难以汇集？
  - 用户希望自己能访问哪些信息，而无需升级到技术团队？
- 最强的问题**既常见又有后果**，因为它们反映组织在真实约束下反复做出、且延迟或出错的代价有意义的决策。
- 起点应在**领导者或运营者能识别出重要状况的层级**，然后向解释该状况的对象与关系移动。一个有用的问题序列通常做三类工作：**Establish the situation**（识别需要注意的客户、设施、资产、组合或运营结果）→ **Trace the contributing factors**（沿关系追踪该结果背后的订单、事件、物料、头寸或观察）→ **Assess the impact**（确定该状况还影响什么、使什么面临风险、团队可以在哪里介入）。
- **重要规则**：若 Ontology 无法自然表达一个重要问题，**把该问题保留在问题集中，而不是替换它**。**把这次失败本身当作一个结果**，并审查设计是否缺少领域概念、关系或某段业务逻辑。

**C. 演练设计的三个决策（Drill design decisions）**
- 决定一次演练能揭示多少的三个决策：**参与者可以用哪些工具、谁参与、以及他们独自还是以团队形式工作**。
- **工具**：专用应用（purpose-built applications）可以通过预先把正确的起点、路径、过滤器与计算编码进去，**补偿 Ontology 设计的弱点**。一个构建良好的 Workshop 应用可以交付出色工作流，却**完全不能告诉你**底层模型是否可被独立发现与表达。**演练应排除这些应用。**
- **谁参与**决定结果的含义：① 有经验的构建者展示的是**在完全了解实现细节的情况下**什么是可能的；② **没有构建过该 Ontology 的领域专家**，能对「其名称、描述与关系是否能独立传达信息」提供更强的证据；③ **较新的用户**测试模型是否能支持上手（onboarding），而不是依赖机构记忆。
- **团队与个人形式**揭示不同属性：团队演练测试**共享流畅度**，并显示用户如何向彼此解释模型；个人演练则隔离出对不熟悉该 Ontology 的人的可用性。使用团队形式时，**应先进行无协助尝试，再允许指导**，以免集体专长掩盖最初的困惑点。
- 该演练衡量的是 **Ontology 代替参与者做了多少工作**；这使**你记录的观察与收集到的答案同样有价值**。

**D. 如何读结果（Reading the results）**
- **正确性只是最低要求**。运营价值还取决于用户能多快识别答案、解释路径、并有信心地行动。
- 对每个问题，记录参与者是否得出正确答案，以及调查耗时。记录参与者在哪里犹豫、搜索了哪些术语、尝试了哪些 object types 与 links、以及是否需要帮助。**手工导出与手工 join 是特别重要的信号：它们常常表明业务中存在某个有意义的关系，但 Ontology 中没有。**
- **通向答案的路径可能比最终答案更有信息量**。当参与者困惑时，问他们期望找到什么；他们的说法可以指出缺失的别名、不清楚的描述、或领域中直观但模型中缺失的关系。意外的路径既可能揭示有用的替代方案，也可能揭示导致结果不一致的含糊之处。
- **症状 → 应复查内容的对照表（原文）**：

| 你观察到的现象 | 应复查什么 |
| --- | --- |
| 用户无法识别起始 object type | 名称不清、别名不足、可见类型太多、或缺少描述（**The Misnomer**） |
| 用户为同一概念选择了不同 object types | 重复、重叠或区分不足的概念（**Department Silos**） |
| 用户无法在他们认为相关的概念之间移动 | 缺失、命名错误、方向错误或不可用的 link（**Link design**） |
| 用户导出数据或手工构造 join | Ontology 未表示的某个有意义的关系或可复用分析概念（**Link design**） |
| 合理的路径得出不同答案 | 细节层级不清（如 order 与 order line 或 shipment 的对比），或身份、单位、日期、聚合逻辑含糊（**Naming conventions**） |
| 只有构建者或深度技术用户能成功 | 源系统术语、隐藏约定或文档不足（**System Silos**） |
| 一条合理路径持续很慢 | 查询、索引、数据量或建模性能约束（**Normalization and derived properties**） |
| 没有任何合理路径能回答该问题 | 缺失数据、领域覆盖缺口、或不支持的分析操作 |

- **并非每个困难任务都需要改动 Ontology**。首先要判断约束是在模型、底层数据、权限、分析应用还是用户培训中。把一次失败当作可能的边缘情况，而把围绕同一 object type 或关系的反复困惑当作系统性设计问题的证据。要把模型问题与知识问题分开，**可以不带人类参与者再跑一遍同样的问题**。

**E. 比较人与 agent（Comparing people and agents）**
- Ontology 服务两类消费者：**人**与 **AI agents**。二者带来不同能力：人贡献领域经验、组织上下文与隐性知识；agents 能搜索与转换大量数据、测试多条路径，且不像人那样依赖视觉层级。
- **做法**：在完成一次人工演练后，用 **AIP Analyst** 或 **AI FDE** 跑同样的问题。提供问题与必要的 Ontology 访问，但**不要提供人类参与者所走的路径**。
- **比较揭示 Ontology 让哪些知识变得显式（原文表）**：

| 结果 | 应调查什么 |
| --- | --- |
| 人与 AI 都成功 | 确认该模型为这个问题提供了可发现且可表达的路径 |
| AI 成功但人struggle | 复查面向人的名称、别名、描述、默认视图与视觉层级；也要考虑该任务是否天然更适合规模化自动分析 |
| 人成功但 AI struggle | 找出参与者凭经验提供、而 Ontology 未显式表达的业务逻辑或领域知识 |
| 人与 AI 都 struggle | 寻找缺失的数据、links、语义或可复用业务逻辑 |

- 文档强调：**只跑 AI 不能替代与人一起测试**。它评估的是另一个属性：Ontology 是否包含足够的上下文，让 agent 能在不依赖团队未成文知识的情况下推理。**这与构建者凭记忆弥补的是同一个缺口，只是在全组织尺度上**。如果人之所以成功只是因为他们已经懂业务，那份知识仍然难以自动化、也难以传授给新人。

**F. 两种演练形式（Exercise formats）**
- Palantir 使用两种互补演练：**quiz-style game（测验式游戏）**覆盖**广度**——许多独立问题，测试对 Ontology 不熟悉者的可发现性；**timed drill-down（限时下钻）**覆盖**深度**——测试团队能否从组织级问题持续进行一条连贯调查直到细粒度运营细节。

**Quiz-style game（测验式游戏）**
- 形式：团队之间的竞赛。时间压力迫使参与者承诺一条路径，并让该路径可见。因为问题事先未知，没有团队能带着为某题预先构建好的工作流到场。该形式也具参与感与互动性。
- 运行指引（原文）：
  - **在游戏开始前隐藏问题**：团队可以通过熟悉自己的 Ontology 来准备，但不能排练某个具体分析。
  - **给更困难的问题分配更高分值**：低分值问题需要直接查找、计数或单对象调查；高分值问题需要跨多个 object types 与 links 的多步分析。
  - **指定一名参与者操作应用**：要求每个团队提名**最不熟悉该 Ontology** 的参与者来操作应用。其他成员可以指导、解读问题、建议路径。该结构同时测试「对不熟悉 Ontology 的人的可用性」与「团队传达其共享模型的能力」。
  - **只使用通用分析应用**：允许 **Insight**、**Contour** 与 **Quiver**，排除专用 **Workshop** 应用以及 **AIP Analyst**、**AI FDE** 等 AI 协助。该约束让**Ontology** 而不是准备好的界面或 agent 处于演练中心。
  - **要求团队展示其工作**：把分数给第一个产出答案并向裁判演示其分析路径的团队。**不接受没有支撑的数字。**

**Timed drill-down（限时下钻）**
- 推荐第二种演练以测试**深度、连续性与速度**，沿着一条连贯的分析路径。团队从一个宽泛问题开始，然后跟随一串固定顺序的问题进入底层运营细节。
- 运行指引（原文）：
  - **构建一条连贯的序列**：让每个问题都依赖前一个问题确立的答案或上下文。
  - **从组织级视图移动到细粒度细节**：测试 links 是否支持跨多个层级与领域的自然调查。
  - **测量总完成时间**：最快团队获胜，但每个团队的时间与分析路径都为设计提供证据。
  - **竞赛是可选的**，在两种形式中都是：其价值在于它创造的紧迫感与专注，而不是排名本身。

**G. 示例问题（原文按行业列出，每组遵循同一「establish → trace → assess」的从宽到细顺序）**
- 文档说明：把它们改编成你组织的语言、决策与职责。

**制造（Manufacturing）**：今年订购产品量最高的客户是哪个？该客户的订单量中哪个产品占最多？哪些工单生产该产品？那些工单需要哪些组件（**包括物料清单中向下多层**）？该建造地点缺少哪些必需组件？哪个供应商延期使最多已排定工单面临风险？

**医疗（Healthcare）**：本季度预约取消率最高的机构是哪个？哪个专科对该比率贡献最多？哪些预约类型占多数取消？哪些取消原因占那些预约的多数？哪些机构有容量重新安排受影响的预约？还有多少即将到来的预约仍面临取消风险？

**物流与分销（Logistics and distribution）**：本月迟交量最高的区域是哪个？该区域中哪个配送中心贡献最多迟交？哪些客户订单占最大份额？哪些货运履行那些订单？哪些路线段或处理事件对延误贡献最多？哪些即将到来的交付走相同路线或经过相同瓶颈？

**金融服务（Financial services）**：哪个组合的集中度风险最大？哪个行业对该集中度贡献最多？哪些发行人与头寸构成该敞口？哪些近期交易增加了该敞口？哪些关联风险事件可能影响那些头寸？哪些拟议交易会超出该组合的风险限额？

**传感器分析（Sensor analysis）**：本月产量缺口最大的机构是哪个？哪些资产对该缺口贡献最多？产量下降前哪些传感器读数发生了变化？哪些维护事件或运行条件与那些变化同时发生？同样的传感器模式以前在哪里出现过？当前还有哪些其它资产显示相似模式？

**国防情报（Defense intelligence）**：某个关注区域有多少艘船？哪些舰船类别占该区域活动的大部分？哪些具体船只最近进入该区域？那些船在进入该区域前走了哪些路线？它们沿那些路线访问了哪些港口？同期它们还与哪些其它船只相遇？

**国防行动（Defense operations）**：哪个单位当前战备水平最低？哪些下属单位对该战备缺口贡献最多？那些单位未满足哪些战备要求？哪些维护行动或供应短缺制约了那些单位？哪些支援单位或地点能提供所需资源？哪些计划演练与预计恢复日期冲突？

**H. Validation as an ongoing practice（作为持续实践的验证）**
- 单个设计周期不会产出完成的 Ontology。领域在演化，运营条件在变化，新的决策对模型提出新要求。应**维持这个过程**：反复测试能显示 Ontology 是否仍以人与 agent 可用的形式代表组织。
- 一次初始演练只需要：**一小部分有后果的问题、未构建该模型的代表性参与者、一个通用分析应用**。由一名**facilitator（引导者）**记录准确性、时间、困惑与协助情况。
- 演练之后，**优先处理影响多个问题或阻塞高价值工作流的改动**。重复部分问题以度量改进，然后引入**没见过的问题**以判断该改进是否能泛化。
- 随着时间推移，**问题集会成为 Ontology 的评估套件（evaluation suite）**。用它来评估新的 object types、links、数据源与业务逻辑是否满足模型必须支持的决策。每次演练的教训会累积成更清晰的语义、更完整的组织上下文与更快的调查。
- **结论（原文）**：一套完整的期望 object types 清单、或一位最终能拼出答案的专家，**都不能**验证一个 Ontology。**人与 agent 必须能反复地从一个有后果的问题出发、沿一条反映组织实际运作方式的路径，走到一个可信的答案。**

---

## 7. 本地文件里没查到 / 语焉不详

> 本节只列「在所读文件中确实找不到、或文档本身自认不完整/不确定」的内容，不做任何推测性填充。

### 7.1 Ontology Manager 界面结构（第 3 节相关）

1. **没有一份完整的左侧导航条目清单。** 文档从未集中列出 OMA 侧边栏的所有条目。第 3.2 节的条目（Object types / Link types / Action Types / Shared Properties / Interfaces / Functions / Unsaved changes / History / Proposals / Main branch updates / Advanced settings / Cleanup / Conflicts / Errors / All changes）是从多个不同页面零散提及中拼出的，**无法确认它们是否同属一个侧边栏、分组方式与顺序如何**。`ontology-manager__navigation` 只描述了搜索、首页过滤器与 Back home，未列举侧边栏。
2. **对象类型 Overview 页 7 个分区只给了名称，没有内容说明。** `ontology-manager__overview` 按编号列出 Object type metadata、Properties、Action types、Link type graph、Dependents、Data、Usage，但**没有逐一说明每个分区放什么**。其中 **Dependents** 与 **Data** 仅有名称，全文再未出现任何描述。
3. **Property editor view（属性编辑器视图）内部结构未描述。** 文档只说「从 Properties 区选一个 property 打开该视图」，未列出其分区或字段。
4. **各资源视图的侧边栏页签未穷举。** Link type view 只写 Overview 与 Datasources；Action type view 只写 Overview、Logic、Observability（另有 Parameters、Rules、Security & Submission Criteria、Capabilities 分散在其它页面被提及）；Function type view 只写 Overview、Configuration、Observability。**无法确定这些是否就是完整的页签集合。**
5. **Capabilities 页签的完整内容未描述。** 它被 Vertex link merging（「Ontology Manager 的 Vertex Ontology Capabilities 区」）与 action log（Create action log objects 区）两处提到，但**不在 `ontology-manager__overview` 列出的视图清单中**，其整体包含哪些能力区未被说明。
6. **Discover view 的可配置区块**：只列出 "Recently viewed object types"、"Favorite object types"、"Favorite groups" 以及「可为特定 group 添加区块」。是否还有其它可添加区块**未说明**。
7. **顶栏「创建新 Ontology 资源」的具体入口与表单未描述**。

### 7.2 变更与治理（第 4 节相关）

8. **破坏性改动的完整清单缺失。** `ontology-manager__save-changes` 明确引用「potential breaking changes」文档，但**该文档不在 clean 目录的文件列表中**（目录中无对应文件），因此**哪些改动是破坏性的、各自后果如何，本地完全没有**。已知的仅有两条分散提示：对 object types 及其属性的编辑可能对依赖应用造成破坏性影响；若对象类型启用 writeback，需格外小心不要移除编辑历史。
9. **保存时的合并冲突解决细节不足。** 只说明可在「保留 Ontology 最新版本中的改动」与「用自己工作状态中的改动覆盖」之间选择，**具体 UI、是否逐字段、冲突如何呈现均未描述**（对比之下，branching 文档的 rebase 冲突处理描述详细得多）。
10. **`OntologyMetadata:` / `Phonograph2:` 错误码清单缺失。** 文档只说「在文档中搜索该错误名」，未给出清单；本次文件中只出现 `OntologyMetadata:UnreferencedRuleSets` 一个具体错误码。
11. **Export/import 的 JSON 结构完全未描述**，且文档**明确声明**「不应依赖导出的 JSON schema，因为它可能随时间变化」。因此无法知道导出文件的字段、版本兼容策略。
12. **导入到「另一个 Ontology」的完整限制未说明。** 只知道带 conditional formatting rules 的工作状态不能导入到别处。其它配置（如 action log、link merging、interfaces）能否跨 Ontology 搬运**未提及**。
13. **Cleanup 的 flags 列表文档自认不穷举**（原文「is not exhaustive」）；**默认 flag 集合包含哪些、各自的默认优先级顺序如何，均未给出**。自定义 flag 与默认集合的差异规则只给了「未来新增 flags 不会自动打开」这一条。
14. **Cleanup 的权限与角色要求未说明**：谁能访问 cleanup 工具、谁能执行 Delete、删除是否受对象类型权限约束，均未提及。
15. **Usage 指标的「内部表未配置」问题无自助解决路径**，文档只建议「联系你的 Palantir 代表」。
16. **Ontology roles 的具体粒度与授予流程缺失。** `ontology-core-concepts` 说 roles 可授予在 Ontology 级或单个资源级；`branching` 提到 protected resources 必须先迁移到 project permissions。但 roles 的完整模型、迁移步骤细节在引用的 **「Ontology roles migration [Legacy]」**、**「Migrate to project-based permissions」** 页面中，**这两个页面不在本次文件内**。
17. **资源的 visibility 与 development status 取值未列出。** 首页列表可按 visibility、development status、indexing issues 过滤，但**这些枚举的具体取值没有说明**。
18. **Action log 的「scale 与 property 限制」只是一个引用**（"the same scale and property limits as other object edits"），具体数值不在本次文件中。
19. **`Edits` provenance 的配置方法未描述**（只说 function-backed action 的 backing function 必须配置它，指向 functions 文档）。
20. **动作撤销（undo / revert actions）机制未描述**，只在 action log 的「选择哪种能力」对照表与 action metrics 的 Next steps 中被提及名称。
21. **Action metrics 与 monitoring rules 的内容缺失**。action type 的 Observability 页签提到「监控规则及其状态」，`ontology-manager__overview` 指向「Review action rules」文档，**该文档不在本次文件内**；action metrics 本身也没有本次文件。

### 7.3 图与探索（第 5 节相关）

22. **文档没有 Vertex 与 Object Explorer 的直接对比。** 第 5.3 节的对照表是对两份文档各自陈述的归纳，**不是文档给出的结论**；文档也没有说在什么场景下应优先选哪一个。
23. **Vertex 的侧边栏/页签全貌未穷举。** 散见 **Selection**（对象选择面板）、**Events**（对象选择侧边栏内）、**Histogram**（侧边栏）、**Layers**（侧边栏）；**Search Around** 面板为工作区右侧页签，另有顶部工具栏的 **Selection** 菜单与 **Parameters** 按钮。完整界面结构未被文档集中描述。
24. **Vertex 的「发布/共享/协作」未描述。** `vertex__overview` 说可访问「已由组织整理并发布的图」，`graphs-template` 的上一页是 **Save, share, and collaborate**、下一页是 **Generate a graph from other applications**——**这两页均不在本次文件内**，因此图的保存、共享、权限、以及从其它应用生成图的细节都没有。
25. **Vertex 的 `system graphs` 未定义。** overview 提到「build new system graphs」，但未说明它与普通 graph 的区别。
26. **Vertex 的 Example use cases 页不在本次文件内**（overview 的 NEXT 指向它），因此官方给出的具体用例清单缺失。
27. **`vertex__link-merging` 全文仅 15 行**，只说明配置位置与作用；`link via` 选项在 Search Around 菜单中的具体形态、以及 link merge 与「Group nodes into edge」的对应关系只有一句交叉引用，**未展开**。
28. **Vertex 时间选择面板（time selection panel）的可用选项未描述**（只描述「拖动游标 scrub」这一交互与动态样式效果）。
29. **Object Explorer 的搜索语法（search syntax）未包含。** `search-objects` 的 NEXT 指向 **Search syntax** 页，不在本次文件内；因此查询语法、算子、字段限定等具体规则缺失。
30. **Object Explorer 的以下能力只有名称、无细节**（它们分别是相邻页面的标题）：**Save lists**、**Compare object sets**、**Explore with charts**、**Generate Object Explorer URLs**。文档只说可以保存 Explorations、对比对象集、用 exploration view（图表/地图）下钻、以及打开到其它应用，但**具体操作与限制未描述**。
31. **Object Explorer 的探索入口归属未说明**（Workspace 侧边栏哪个分组），与 Vertex 明确写「Apps → Operational Applications」形成对比。
32. **Object Explorer 的权限模型未描述**（谁能在 Object Explorer 中看到哪些对象、批量动作的权限如何检查，只在 actions 文档提到「Actions 不可用」的 1000 对象上限）。
33. **Object Views 的 widget 全集未覆盖。** 本次只读了 **Properties**、**Property Cards**、**Links**、**Edit History** 四类（properties-links 类）；该文件的分页器显示 NEXT 为 **Visualization**，另有 **Configure profiles** 为上一页——**可视化类 widget 与 profiles 的配置均不在本次范围内**。
34. **Object Views 中对 Actions widget 的完整配置未描述**（仅从 action-types 入门得到「复制 action RID → 粘贴 → 配置默认值与 Hidden」这一条路径）。
35. **「Actions widget」「Action Log Timeline widget」「Comments widget」等 widget 的完整参数清单缺失**（它们分别在不同文档中被提及用途）。

### 7.4 设计规范（第 6 节相关）

36. **derived properties 各聚合操作的相对性能**：文档只说「参阅 derived properties reference」，**该参考页不在本次文件内**；「> ~1 万个对象」是文档给出的唯一量化阈值，且带有波浪号（近似）。
37. **structs 的字段类型能力、reducer 类型清单、main field 在 interface/query 中的确切行为**只有概括描述（「可指定一个或多个 main fields」「使用 reducers 呈现最相关的值」），**具体类型与选项未列出**。
38. **interfaces 平台支持的现状未描述。** 文档说「参阅 interface documentation 了解当前支持详情」，并承认「某些情境尚未支持」，但**哪些情境支持、哪些不支持没有在本文件中说明**（`interfaces__interface-overview.txt` 存在于 clean 目录，但不在本次清单内）。
39. **security 的配置方法未描述**。文档明确说「参阅 security and governance documentation 了解配置细节」；**行级/列级安全如何实际配置、restricted views 如何使用，只在别处被点名**。
40. **命名的「治理审查」流程未描述**：best practices 说「通过治理审查强制执行」，但治理流程本身（谁审、如何审）不在本次文件内。
41. **Validation 的量化基准缺失**：文档没有给出「回答时间多长算慢」「准确率下限」之类的阈值，只强调记录准确性与时间、并反复测试。
42. **Validation 中提到的 `Insight` 与 `Contour` 应用未做任何定义或说明**（只在允许使用清单中出现名称）；`AIP Analyst` 与 `AI FDE` 也只是名称，无功能描述。
43. **示例问题中各行业的对象模型前提未给出**（文档明确要求「改编成你组织的语言」，未提供配套的 object types/links 设计）。

### 7.5 本次未纳入阅读的相邻文件（存在于 clean 目录，但不在指定清单内）

> 说明：为避免越界，本次**未读取**以下文件；它们可能在上述缺口中包含答案。列出以便后续查阅。

- `action-types__rules.txt`（action rules 细节）
- `interfaces__interface-overview.txt`（interfaces 支持现状）
- `object-link-types__*.txt`（13 个文件：object types / link types / properties / structs / derived properties / value types 等，对应第 6 节结构指引的展开）
- `ontology__why-ontology.txt`
- `object-views__widgets-*` 的其它分册（如 Visualization）若存在
- 其它 21 个 clean 目录中的文件（合计 59 个，本次读取 38 个）

---

### 附：本文所述文档到源文件的索引

| 本文节 | 源文件 |
| --- | --- |
| 1.1–1.2 | `ontology__overview`、`ontology__models` |
| 1.3 | `ontology__core-concepts` |
| 1.4 | `ontologies__ontologies-overview` |
| 2.1 | `ontology-manager__overview` |
| 2.2 | `object-explorer__overview` |
| 2.3 | `vertex__overview`、`vertex__explore-object-relationships` |
| 2.4 | `object-views__overview`、`object-views__widgets-properties-links` |
| 2.5–2.6 | `ontology__applications`、`ontology__core-concepts`、`vertex__link-merging`、`action-types__getting-started`、`action-types__action-log` |
| 3.2–3.9 | `ontology-manager__overview`、`ontology-manager__navigation`、`ontologies__review-ontology-proposals`、`ontologies__branching-ontology`、`ontology-manager__cleanup`、`ontology-manager__export-import`、`object-views__widgets-properties-links`、`action-types__action-log`、`vertex__graphs-display-options` |
| 4.1 | `ontology-manager__save-changes` |
| 4.2 | `ontology-manager__restore-changes` |
| 4.3 | `ontologies__branching-ontology` |
| 4.4 | `ontologies__review-ontology-proposals` |
| 4.5 | `ontology-manager__export-import` |
| 4.6 | `ontology-manager__view-usage` |
| 4.7 | `ontology-manager__cleanup` |
| 4.8 | `action-types__action-log` |
| 4.9 | `action-types__overview`、`action-types__getting-started`、`action-types__parameter-overview`、`action-types__submission-criteria`、`action-types__side-effects-overview`、`action-types__function-actions-overview` |
| 4.10 | `ontology__core-concepts`、`ontology-manager__view-usage`、`ontologies__review-ontology-proposals`、`ontologies__branching-ontology`、`ontology__applications` |
| 5.1 | `vertex__overview`、`vertex__graphs-explore`、`vertex__explore-object-relationships`、`vertex__graphs-display-options`、`vertex__graphs-template`、`vertex__link-merging` |
| 5.2 | `object-explorer__overview`、`object-explorer__search-objects`、`object-explorer__pivot-linked`、`object-explorer__apply-actions`、`object-explorer__view-results` |
| 5.3 | 上述两组文件（归纳） |
| 6.1 | `ontology__ontology-best-practices` |
| 6.2 | `ontology__ontology-structural-guidance` |
| 6.3 | `ontology__ontology-anti-patterns` |
| 6.4 | `ontology__ontology-design-validation` |
