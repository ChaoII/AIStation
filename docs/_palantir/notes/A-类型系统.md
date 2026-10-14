# A-类型系统：Palantir 本体类型系统结构化笔记

> 本笔记**仅**基于本地已抓取的干净正文（`docs/_palantir/clean/`），未联网、未引入外部资料。
> 所有定义、枚举值、约束均来自下列 19 个文件；凡文档未写明之处，一律记入文末「本地文件里没查到 / 语焉不详」，不做推测填充。

## 0. 来源文件清单

| # | 文件 | 主题 |
|---|---|---|
| 1 | [object-link-types__type-reference.txt](../clean/object-link-types__type-reference.txt) | 类型总览（Ontology types vs data types） |
| 2 | [object-link-types__object-types-overview.txt](../clean/object-link-types__object-types-overview.txt) | 对象类型定义、object / object set 区别 |
| 3 | [object-link-types__create-object-type.txt](../clean/object-link-types__create-object-type.txt) | 创建对象类型（向导 + 手工）、必填字段、命名规范 |
| 4 | [object-link-types__edit-object-type.txt](../clean/object-link-types__edit-object-type.txt) | 编辑对象类型、破坏性变更、错误码 |
| 5 | [object-link-types__object-type-metadata.txt](../clean/object-link-types__object-type-metadata.txt) | 对象类型元数据参考 |
| 6 | [object-link-types__properties-overview.txt](../clean/object-link-types__properties-overview.txt) | 属性定义、支持的属性类型表 |
| 7 | [object-link-types__edit-properties.txt](../clean/object-link-types__edit-properties.txt) | 编辑属性、批量编辑 |
| 8 | [object-link-types__property-metadata.txt](../clean/object-link-types__property-metadata.txt) | 属性元数据参考、受限支持类型 |
| 9 | [object-link-types__base-types.txt](../clean/object-link-types__base-types.txt) | 基类型、高级类型、媒体引用 |
| 10 | [object-link-types__derived-properties.txt](../clean/object-link-types__derived-properties.txt) | 派生属性配置、聚合枚举 |
| 11 | [object-link-types__link-types-overview.txt](../clean/object-link-types__link-types-overview.txt) | 链接类型定义、方向性 |
| 12 | [object-link-types__create-link-type.txt](../clean/object-link-types__create-link-type.txt) | 创建链接类型、基数、外键、连接表、对象支撑链接 |
| 13 | [object-link-types__edit-link-types.txt](../clean/object-link-types__edit-link-types.txt) | 编辑链接类型、破坏性变更 |
| 14 | [object-link-types__link-type-metadata.txt](../clean/object-link-types__link-type-metadata.txt) | 链接类型元数据参考 |
| 15 | [object-link-types__shared-property-overview.txt](../clean/object-link-types__shared-property-overview.txt) | 共享属性 |
| 16 | [object-link-types__value-types-overview.txt](../clean/object-link-types__value-types-overview.txt) | 值类型 |
| 17 | [object-link-types__structs-overview.txt](../clean/object-link-types__structs-overview.txt) | 结构体属性 |
| 18 | [object-link-types__type-groups.txt](../clean/object-link-types__type-groups.txt) | 对象类型分组 |
| 19 | [interfaces__interface-overview.txt](../clean/interfaces__interface-overview.txt) | 接口 |

---

## 1. 类型全景：Ontology types 与 data types

**官方分类**（type-reference）：Foundry 中的类型分为两类。

| 类别 | 官方定义（中文转述） | 说明 |
|---|---|---|
| **Ontology types（本体类型）** | 用于把现实世界领域建模进 Ontology | 声明式建模资源 |
| **data types（数据类型）** | 用于表示数据取值（data values） | 官方注明其灵感来自 RDF / OWL / XSD |

### 1.1 Ontology resources（本体资源）六件套

| 资源 | 官方定义（关键句转述） | 英文原词 |
|---|---|---|
| **Object type（对象类型）** | 现实世界实体或事件的**模式定义（schema definition）**，由一个个 object 组成。例：JFK 与 LHR 都是 `Airport` 对象类型的 object | object type |
| **Property（属性）** | 对象类型的一个特征（characteristic），描述现实世界实体或事件 | property |
| **Shared property（共享属性）** | 可在多个对象类型上使用的属性；使跨对象类型的数据建模保持一致，并集中管理属性元数据 | shared property |
| **Link type（链接类型）** | **两个对象类型之间关系**的模式定义；一条 link 指该关系的单个实例 | link type / link |
| **Action type（操作类型）** | 用户可一次性对对象、属性值、链接所做的一组变更/编辑的模式定义，还包含 Action 发生时的副作用行为 | action type |
| **Object type groups（对象类型分组）** | 一种分类原语（classification primitive），帮助用户更好地搜索与探索本体 | object type group |
| **Interfaces（接口）** | 描述对象类型**形状与能力**的本体类型；提供对象类型多态（polymorphism） | interface |

### 1.2 定义（definition / 类型层）与实例（instance / 数据层）的区别

官方明确区分（type-reference「Difference between object types and objects」）：

- **Object type definitions**：类型层信息（如显示名、属性名、属性数据类型、描述）。官方强调：**元数据不包含属性的实际数据或取值，也不含主键取值**——那些属于 ontology data。
- **Object instances**：某个本体实体具体实例的主键与属性取值（例：`Plane ID = my_plane_id1`、`Maximum Occupancy = 240`）。

同样区别适用于 link type 与 link。

### 1.3 与数据集结构的类比（object-types-overview / properties-overview / link-types-overview）

| 本体概念 | 数据集类比 |
|---|---|
| object type 定义 | dataset 定义 |
| object | dataset 的一行（row） |
| object set | 被筛选的一组行 |
| property 定义 | dataset 的一列（column） |
| property value | dataset 中的一个字段（field） |
| link type 定义 | 两个 dataset 之间的 join |
| link | join 后的一行（与另一 dataset 中同一行的字段连接） |

### 1.4 数据如何进入本体

- 对象的产生方式：**添加 backing datasource**，或**配置 actions** 创建对象（object-types-overview）。
- 若所有对象都将由 action 创建，可以**不建 backing datasource 地创建对象类型**（create-object-type）。
- 属性值同理：添加 backing datasource，或用 action 创建（properties-overview）。

---

## 2. Object type（对象类型）

### 2.1 定义

- 官方定义：**object type 是现实世界实体或事件的模式定义**；object / object instance 是对象类型的单个实例；object set 是多个对象实例的集合（object-types-overview）。
- 例：`Employee` 对象类型定义「所有员工」的特征；「Melissa Chang」是一个 object；「所有在职满一定年限的员工」是一个 object set。
- 例：`Flight` 对象类型、`JFK → SFO 2021-02-24` 是一个 object。

### 2.2 元数据完整清单

来源：[object-type-metadata.txt](../clean/object-link-types__object-type-metadata.txt)（官方元数据参考）+ [create-object-type.txt](../clean/object-link-types__create-object-type.txt)（向导与手工创建的补充项）。

| 属性名（官方英文） | 中文含义 | 是否必填 | 取值范围 / 枚举 | 出处 |
|---|---|---|---|---|
| **ID** | 对象类型的唯一标识符，主要在配置应用时引用该类型的对象 | **必填**（保存新对象类型时不可为空） | 小写字母、数字、连字符；首字符必须是（正文）/应为（检查单）小写字母或字母；**跨所有对象类型唯一**；创建后不可编辑 | metadata + create + edit |
| **RID** | Foundry 为每个资源自动生成的唯一标识；对象类型的 RID 会出现在平台错误信息中 | 系统自动生成（不可配置） | 文档仅说明用途，未给出格式规范 | metadata |
| **Icon** | 图片 + 颜色，作为对象类型的视觉标识，在用户应用中展示 | 未列为必填 | 从默认图标集中选择图标与颜色 | metadata + create + edit |
| **Display name** | 访问该类型对象时向用户显示的名称 | **必填** | 自由文本 | metadata + create |
| **Plural display name** | 访问多个该类型对象时显示的名称 | **必填** | 自由文本 | metadata + create |
| **Description** | 关于该对象类型的解释性文本，用户应用中任何人可读（如 Object Explorer 搜索结果中会展示） | 未列为必填 | 自由文本 | metadata + create |
| **Aliases** | 用户搜索时会命中该对象类型的额外词条 | 未列为必填 | 自由文本（可多个） | create（手工元数据小节） |
| **Groups** | 用于归类对象类型的标签，帮助组织本体、便于后续筛选 | 未列为必填 | 可从已有分组列表中选择，或直接输入名称新建；可增删 | metadata + create + type-groups |
| **API name** | 在代码中以编程方式引用该对象类型时使用的名称 | **必填** | PascalCase（UpperCamelCase）；首字符大写；仅字母数字；**跨所有对象类型唯一**；长度 1–100；**active 状态不可修改** | metadata + create + edit |
| **Visibility** | 向用户应用指示该对象类型的展示显著程度 | 未列为必填；**默认 `normal`** | `normal` / `prominent` / `hidden`（prominent 会让应用优先展示；hidden 不出现在用户应用中） | metadata + edit |
| **Status** | 向用户与其他本体构建者表示该对象类型处于开发流程的哪个阶段 | 未列为必填；**默认 `experimental`** | `active` / `experimental` / `deprecated` | metadata + edit |
| **Index status** | 该对象类型及其 backing datasources 上一次重建索引（reindex）的状态 | 系统字段 | `success` / `failed` / `not started` | metadata |
| **Writeback** | 是否已生成 writeback 数据集，以及是否允许终端用户编辑该类型对象 | 系统字段 | 编辑能力：`enabled` / `disabled` | metadata |
| **Backing datasource** | 作为该类型对象属性值来源的数据源；无数据源创建的对象类型此字段无值 | **必填，除非**选择「不带 backing datasource 创建」 | 任一 Foundry 可用 datasource；**一个 datasource 只能支撑一个对象类型**；backing datasource **不得包含 MapType 或 StructType 列** | metadata + create |
| **Title key** | 充当该类型对象显示名的属性（记录在属性上，不是对象类型独立字段） | **必填**（保存前须配置；列入「不可为空的属性字段」） | 须来自「可作为 title key」的基类型（见 §4） | create + property-metadata |
| **Primary key** | 充当该类型每个实例唯一标识的属性 | **必填**（列入「不可为空的属性字段」；每个对象类型只有一个主键） | 须来自「可作为 primary key」的基类型；值须**唯一**且**确定性（deterministic）** | create + property-metadata |
| **Type classes** | — | — | **对象类型元数据参考中未列出**（见文末「未查到」） | — |
| **Render hints** | — | — | **对象类型元数据参考中未列出**（render hints 只在属性元数据中出现） | — |

> 官方「Mandatory object type fields」原文清单：To save a new object type, the following object type fields must not be empty: **ID、Display name、Plural display name、Backing datasource（除非无数据源创建）、API name**。
> 另有「Additionally, the following **property** fields must not be empty」：**Property ID、Property display name、Backing column（除非该属性仅通过 actions 填充）、Property API name、Title key、Primary key**。

### 2.3 创建流程（向导步骤）

官方推荐用 guided step-by-step helper（引导式分步助手），步骤为：

1. **Create a new object type**（从首页 `Create your first object type` 或 `New > Create object type` 启动）
2. **Choose a backing datasource**（选择后会自动填充元数据，并把数据源每一列映射为属性，可在 Properties 步骤丢弃）
   - 数据源可以是「现有 datasource」，也可以「不带 datasource 继续」并为权限生成一个空数据集；**使用 Object Storage v1 时该选项不可用**。
3. **Object type metadata**（Icon / Name / Plural name / Description / Groups）
4. **Create properties for the object type**（**每个对象类型至少需要一个属性**，因为必须有主键；媒体等需要高级配置的属性类型无法在向导中生成，必须在退出向导后添加）
5. **Configure the primary key and title key**
6. **Generate actions**（可选：生成一组标准 action 并指派可运行的用户/组；**Object Storage v1 下该步骤不可用**）
7. **Save location**（选择项目；点 `Create` **只是暂存（stage）修改，不会保存**）
8. **Configure security policies**（**仅当不带 backing datasource 创建时必需**；由数据源支撑的类型继承数据源位置的权限，无需配置策略）
9. **Save change to ontology**（回到 Ontology Manager 右上角 `Save` 才真正生效）

无 datasource 创建时的额外强制要求：对象类型必须保存在项目中（使用 project-based permission model），并配置 **object security policy**；**每个对象类型仍必须有主键，且每个通过 action 创建的对象必须有唯一主键值**。

### 2.4 手工创建（提前退出向导后补齐）

必须在退出助手后自行完成：添加元数据 → 添加 backing datasource → 新增属性 → 映射列 → 配置主键与标题键。属性到列的映射方式有三种：

| 映射方式 | 行为 |
|---|---|
| Map a column to a new property | 悬停列 → `Add as a new property`；属性 ID、显示名、base type 由列名推断 |
| Map a column to an existing property | 若已存在与列名相同的属性 ID，则该列映射到既有属性 |
| Map a property to a column | 在属性面板悬停属性 → `Map to a column`，从下拉选择列 |
| Add all unmapped columns as new properties | 一键为数据源全部未映射列建属性，ID/显示名/base type 由列推断 |

主键与标题键通过属性编辑器元数据面板的 `Primary key` / `Title key` 勾选配置。

**主键关键约束（官方强调）**：

- 每个对象必须有唯一主键值；对数据源支撑的类型，backing datasource **每一行**都必须不同。
- 分配主键前**务必检查重复**：Object Storage v2 下重复主键会导致 **Funnel batch pipeline 错误，进而构建失败**；Object Storage v1（Phonograph）下更新会「看起来成功」，但重复主键可能导致本体出现意外变化。
- 主键除唯一外还应**确定性**：非确定性主键在构建时变化会导致**编辑丢失、链接消失**（本体编辑与对象主键绑定；构建不协调时链接 ID 不更新则链接消失）。应把主键定义为**单列或多列的函数**，避免使用行号编号或随机键生成。
- **编辑永久绑定在编辑时的主键值上**；任何时候更改对象类型主键，都会提示**删除全部既有编辑**。

### 2.5 安全策略（permissions）

- 数据源支撑类型的对象权限**继承自 backing datasource 所在位置**，因此不需要配置策略。
- 无数据源创建的类型须配置 **object security policy**，决定谁能查看通过 action 创建的对象。
- 移除 backing datasource **仅在对象类型已保存于项目中时可用**（确保使用 project-based permission model 而非继承数据源权限）。

### 2.6 编辑对象类型与破坏性变更

**会触发 backing datasources 注销/重新注册（或删除）的变更**（保存后该类型对象在 reindex 期间**不可用**）：

1. 更改对象类型的 backing datasource
2. 更改对象类型的主键
3. 删除对象类型

**已启用 writeback 时的额外风险**：编辑历史存于 Object Storage v1（Phonograph）；每次构建 writeback 数据集都会重放编辑历史。数据源被注销时，**编辑历史被删除，后续 writeback 构建会失败**。除上述三项外，对**任何「曾经收到过编辑」的属性**（即使当前不再收到编辑）做 schema 变更（**包括属性 ID 与 base type 的变更**）也需要注销。

**不**需要注销、因此不冒编辑历史丢失风险的变更：

- 更改**已收到编辑属性**的 display name、title key、render hints、type classes、visibility。
- 删除字段、或对**从未收到编辑**的字段做 schema 变更。

**重要机制**：Object Storage v1 **不会**因这些 schema 变更自动注销数据源，而是**reindex 失败**；只有撤销已保存的 schema 变更，或在该对象类型 `Datasource` 页的 `Phonograph` 面板手动注销+重新注册，reindex 才会成功。属性面板会高亮标明某字段是否曾经收到过编辑。

**编辑入口与限制**：

- 更改 backing datasource：属性编辑器 → `Datasources` 面板 `Replace`；**仅当新数据源与旧数据源 schema 相同时属性才会自动重新映射**，否则需手工重映射。
- 无数据源类型添加数据源：`Edit property mapping` → `Add a backing datasource` → 映射列 → 检查安全配置 → 保存。
- 移除 backing datasource：原先映射到该数据源的**每个属性都会变为 edit-only 属性**（值改由 actions 填充）。
- 可在对象类型编辑的元数据中直接改：Icon、Display names 与 Description、**Status**（下拉：deprecated / experimental / active）、**Visibility**、**API name**。
- **对象类型 ID 在初次创建流程之后不可编辑。**

### 2.7 编辑对象类型时的官方错误码

| 错误 | 官方解释 |
|---|---|
| `Phonograph2:DatasetAndBranchAlreadyRegistered` | 用于支撑的对象类型的数据源已在支撑本体内另一个对象类型，不能重复使用 |
| `Phonograph2:FoundryColumnNameNotFound` | 支撑数据源中某列被移除，导致某属性未映射；该属性需要重新映射或被删除 |
| `Phonograph2:InvalidColumnRemoval` | 被移除的列支撑着一个**已收到编辑**的属性；需把列加回，或注销并重新注册对象类型 |
| `Phonograph2:InvalidColumnFieldSchemaChange` | 一个**已收到编辑**的属性其 ID 或 key 被更改；需回退变更，或注销并重新注册 |
| `OntologyMetadata:IncompatibleFoundryFieldSchemaForPropertyType` | 试图保存的属性 base type 与其支撑列类型不兼容（例：列类型改为 string，却映射到 integer 属性） |
| `Phonograph2:SchemaMismatch` | 有意改了支撑 schema 但尚未在本体管理器中更新属性类型 |
| `FieldTypeIncompatibleWithOntologyPropertyType` / 「Failed to Update Object Type in Phonograph」 | 数据集数据类型与本体期望的数据类型不匹配 |

---

## 3. Property（属性）

### 3.1 定义

- 官方定义：**属性是对象类型某个特征的 schema 定义**；property value 指某个对象上该属性的取值，即真实世界实体或事件的单个实例（properties-overview）。
- 例：`Employee` 对象类型可有 `employee number`、`start date`、`role` 属性；「Melissa Chang」的属性值为 `11502` / `October 9, 2016` / `software engineer`。
- 官方限定：**每个对象类型至少需要一个属性**（object types need a primary key）。

### 3.2 属性元数据完整清单

来源：[property-metadata.txt](../clean/object-link-types__property-metadata.txt) + [edit-properties.txt](../clean/object-link-types__edit-properties.txt) + [create-object-type.txt](../clean/object-link-types__create-object-type.txt)。

| 属性名（官方英文） | 中文含义 | 是否必填 | 取值范围 / 枚举 |
|---|---|---|---|
| **ID** | 属性的唯一标识符，主要在配置应用时引用该属性 | **必填**（列入不可为空的属性字段） | 小写或大写字母、数字、连字符、下划线；应以字母开头；**同一对象类型内唯一**；保存并被应用引用后，**任何 ID 变更都会破坏应用** |
| **Display name** | 访问该属性值的用户可见名称 | **必填** | 自由文本 |
| **Description** | 关于该属性的解释性文本 | 未列为必填 | 自由文本 |
| **RID** | 自动生成的全局唯一资源标识，会出现在平台错误信息中 | 系统自动生成 | 文档未给格式 |
| **Status** | 表示该属性处于开发流程的哪个阶段 | 未列为必填；**默认 `experimental`** | `active` / `experimental` / `deprecated`；**active 属性不可删除**，且 **active 时不可改 API name** |
| **API name** | 在代码中以编程方式引用该属性时使用的名称 | **必填** | camelCase；首字符小写；仅字母数字；**同一对象类型内唯一**；长度 1–100；active 状态不可修改 |
| **Keys** | 指示该属性是否为对象类型的 title key 或 primary key | **必填**（title key 与 primary key 都列入不可为空字段） | 布尔标记；**active 状态下不可更改主键** |
| **Base type** | 表示该属性取值的类型，并决定用户应用中可用的操作集合 | 必填（须与支撑列类型兼容） | 见 §4 完整清单 |
| **Value formatting** | 依据 base type 可用的数值格式化、日期时间格式化、用户 ID 与资源 ID 格式化，把原始值转为更可读形式 | 未列为必填 | 可用性取决于 base type |
| **Conditional formatting** | 施加在属性上的规则，决定该属性值在面向用户的应用中如何渲染（如配色、对齐） | 未列为必填 | 规则集（例：`full name` 在 `start date` 早于两周时显示绿色） |
| **Type classes** | 供应用解释的附加元数据 | 未列为必填 | **本地文件未给出清单** |
| **Render hints** | 向用户应用指示该属性的渲染方式（可不同于同 base type 的多数属性）；许多 render hints 会影响该对象类型 reindex 的性能 | 未列为必填 | 本地文件仅举例 **`searchable`、`sortable`**（取消勾选可提升 reindex 性能）；完整清单未给出 |
| **Visibility** | 向用户应用指示该属性的展示显著程度 | 未列为必填；**默认 `normal`** | `normal` / `prominent` / `hidden` |
| **Backing column** | 该属性映射到的 backing datasource 列 | **必填，除非**该属性仅通过 actions 填充（edit-only） | 须与 base type 兼容，否则报错 |
| **Edit-only（编辑专用）** | 移除 backing datasource 后，原先映射到该数据源的每个属性变为 edit-only 属性，其值通过 actions 而非数据源列填充 | 不是配置字段，而是一种属性状态 | 官方在「不可为空字段」中以「除非该属性仅通过 actions 填充」表述 |

**属性配置在 UI 中分为四个 tab**（edit-properties 官方描述）：Display name and description / Status / API name；Keys；Value formatting、Conditional formatting、Property base type；Type classes、Render hints、Visibility。

**编辑属性的操作要点**：

- 删除属性：属性面板悬停 → `Delete property`；**保存后才生效，且会破坏引用了该属性的视图或应用**；**active 状态的属性不能删除**。
- 更换支撑列：`Unlink property` 解除，再用 `Map to a column` 重新关联。
- 改 base type 后**必须同步更新与该属性交互的 Actions 所期望的类型**（在 Ontology Manager 打开该 Action 修改 expected type）。
- 改完属性元数据后**需要触发受影响对象的 re-index** 才能更新本体。
- 官方错误：若属性类型与其支撑列类型不兼容，会收到错误。

**批量编辑**（edit-properties）：

- 在属性编辑器中按住 `Cmd/Ctrl` 多选属性后，可批量执行：更改 **base type**、增加/移除 **type classes**、更改 **render hints**、更改 **visibility**、增加/移除 **value formatting**。
- 也可在对象类型侧边栏的 `Properties` 页勾选多个属性批量编辑（顶部出现批量编辑行）。

### 3.3 支持的属性类型（title key / primary key 有效性）

官方原文表（properties-overview）——**这是判断某 base type 能否作为标题键/主键的唯一权威表**：

| 分组 | Property base type | 可作 title key | 可作 primary key | 官方 Notes |
|---|---|---|---|---|
| Commonly used | `String`、`Integer`、`Short` | 是 | 是 | — |
| Time-based | `Date`、`Timestamp` | 是 | **Discouraged（不推荐）** | 时间值通常不适合做主键：存储格式与显示格式不同可能导致意外的碰撞/唯一性问题；多数情况建议改用 `String` |
| Number-like | `Boolean`、`Byte`、`Long` | 是 | **Discouraged（不推荐）** | `Boolean` 会把对象类型限制为两个对象实例；`Byte` 属性只能在 Actions 中通过 `Integer` 参数赋值，多数情况建议用 `Integer`；`Long` 在 JavaScript 中有表示问题，大于 1e15 的值并非所有前端库/代码都能正常处理，多数情况建议用 `String` |
| Float-like | `Float`、`Double`、`Decimal` | 是 | **否** | — |
| — | `Vector` | **否** | 否 | — |
| — | `Array` | 是（有前提） | 否 | 数组**不能含 null 元素**；若 `Array` 的内层类型不是有效 title property，该 Array 属性也不能作 title property；**Object Storage v2 不支持嵌套数组** |
| — | `Struct` | 否 | 否 | Struct 属性不支持嵌套，字段不能是数组；支持的字段类型见 §4.3 |
| — | `Media Reference`、`Time Series`、`Geotemporal Series`、`Attachment` | 否 | 否 | — |
| — | `Geopoint` | 是 | 否 | Geopoint 值以逗号分隔字符串存储，格式 `latitude,longitude`（例 `57.64911,10.40744`） |
| — | `Geoshape` | 否 | 否 | — |
| — | `Marking` | 否 | 否 | — |
| — | `Cipher` | 是 | 否 | — |

### 3.4 受限支持（Limited support）的属性 base type

官方标注 `Limited support` 标签的类型（property-metadata）：

| Base type | 限制 |
|---|---|
| `byte` | 不能用于 action types |
| `float` | 不能用于 action types |
| `short` | 不能用于 action types |
| `vector` | 只能用 KNN 查询；**向量最大维度 2048** |

---

## 4. Base types（属性基类型）

### 4.1 定义与规则（base-types）

- **官方定义**：property base types 定义属性中可以存储的数据种类；base type 决定用户应用中该属性可用的操作集合。
- **所有 field type 都是合法 base type，除了 `Map` 与 `Binary`。**
- 高级类型（advanced types）：

| 高级类型 | 官方定义 |
|---|---|
| **Vector** | 在对象上存储向量、用于语义搜索的类型 |
| **Geopoint** | 表示地理位置**点**的属性类型 |
| **Geoshape** | 表示地理**形状**的属性类型 |
| **Attachment** | 在对象上存储文件、用于 functions on objects 的类型 |
| **Time series** | 把属性定义为时间序列的类型 |
| **Geotemporal series** | 把属性定义为对地理时序序列引用的类型 |
| **Media reference** | 定义对媒体文件引用的类型 |
| **Cipher text** | 存储用 Cipher 编码的字符串值的类型 |
| **Struct** | 定义带多字段的、基于 schema 的属性的类型 |

- **数组规则**：所有 base type 都可用于数组中表示多值，**除 `Vector` 与 `Time series` 之外**。

### 4.2 Media reference（媒体引用）

- 官方定义：media reference 属性类型让你在对象上拥有媒体（图片、视频、音频、文档）；一个 media reference 指向 media set 中的一个具体媒体项；reference 内含媒体文件信息，因此 Foundry 能在任何使用该引用的地方显示媒体。
- **数据格式字段**（官方示例 JSON 的全部字段）：

| 字段 | 含义 |
|---|---|
| `mimeType` | 文件的媒体类型（例 `image/png`） |
| `reference.type` | 示例值 `mediaSetViewItem` |
| `reference.mediaSetViewItem.mediaSetRid` | 媒体集 RID |
| `reference.mediaSetViewItem.mediaSetViewRid` | 媒体集视图 RID |
| `reference.mediaSetViewItem.mediaItemRid` | 具体媒体项 RID |

- **配置要求**：带 media reference 属性的对象类型由 dataset 支撑；**backing dataset 必须包含一个 media reference 列**并映射到该属性。此外，media reference 属性**必须有一个或多个 media sources**，在对象类型的 **`Capabilities` tab** 配置；若有多个 media source，可指定其中一个作为 **`Upload destination`**，控制通过本体编辑上传的媒体项存入哪个 media set。

### 4.3 Struct（结构体属性）

- **官方定义**：struct 是一种本体属性 base type，让单个属性承载**多个字段**而不是一个值；字段在定义属性时声明，每个字段有自己的名字与类型（例：`Full Name` 含 `firstName`/`lastName`；`Address` 含 `street`/`city`/`postalCode`/`country`）。
- **支撑方式**：struct 属性由**单个数据源列**支撑，该列类型本身是 struct；在 Ontology Manager 中把该列选为属性的 **`Backing column`**。字段值可以来自不同数据源，只要在定义本体属性前合并成单个 struct 类型列。
- **官方约束**：

| 约束 | 原文要点 |
|---|---|
| 不允许嵌套 | 一个 struct 属性不能包含另一个 struct |
| 字段不能是数组 | 但 struct 属性本身可以是 struct 数组 |
| 至少一个字段 | struct 属性必须至少有一个字段 |
| 字段类型白名单 | 目前仅支持：`BOOLEAN`、`BYTE`、`DATE`、`DECIMAL`、`DOUBLE`、`FLOAT`、`GEOPOINT`、`INTEGER`、`LONG`、`SHORT`、`STRING`、`TIMESTAMP` |
| 存储版本限制 | **Object Storage v1（Phonograph）不支持 struct**；目前只能从数据集与受限视图（restricted views）创建 struct 属性 |

- **查询语义**：struct 的索引方式类似 ElasticSearch 的 object field 类型，**查询对每个字段条件独立求值**；当 struct 属性持数组时，即使数组中没有任何单个 struct 同时满足全部条件，查询仍可能命中该对象。官方示例：对象存 `[{"firstName":"Ada","lastName":"Chen"},{"firstName":"Blake","lastName":"Moreau"}]`，查询 `"firstName":"Ada" AND "lastName":"Moreau"` 会命中。
- **当前支持范围**：Ontology Manager（定义与编辑）、Actions（创建与修改 struct 属性值）、Pipeline Builder（定义与编辑）、Workshop（作为变量展示与使用）、Marketplace（打包与安装）、Object Explorer（按 struct 属性值搜索对象，**struct 字段搜索仍在开发中**）、Ontology SDK（加载 struct 属性并按值搜索，**并非每个 SDK 都支持**）、Functions（**TypeScript v2 与 Python** 支持 struct 参数与 struct 属性编辑）。

---

## 5. Derived properties（派生属性）

> 官方标注 **Beta**：Ontology-defined derived properties 处于 beta 阶段，可能不在你的 enrollment 上可用，功能可能变化。

### 5.1 定义

- 官方定义：**派生属性在运行时根据链接对象的值计算得出**；不直接存储数据，而是从通过 link type 连接的对象上拉取信息，可选择施加聚合（如求平均、计数、收集成列表）。

### 5.2 配置步骤（官方 7 步）

| 步骤 | 操作 |
|---|---|
| 1 | 对象类型 `Properties` tab → `New property`，或选择既有属性编辑；打开属性配置侧栏 |
| 2 | 侧栏选择 **`Source`** tab，配置属性取值来源 |
| 3 | 在 `Source type` 中选择 **`Linked objects`**（启用派生属性配置） |
| 4 | 在 `Linked objects` 中从下拉选择 **link type**；下拉列出当前对象类型所有可用 link type；选中后可**最多再叠加至三层**链接跳转（`Add linked object`） |
| 5 | 配置 **Aggregation**（若链上任一 link 可到达多于一个对象，则**必须**选择聚合） |
| 6 | 选择要派生的 **property**（下拉列出链接链末端对象类型的所有可用属性）；选择 `Count` 时无需选择属性，对象自动计数 |
| 7 | 若选了 `Collect list` / `Collect set`，可配置 **collection limit** |

### 5.3 聚合（Aggregation）取值清单

| 聚合 | 官方含义 |
|---|---|
| `Count` | 统计链接对象的数量 |
| `Average` | 计算数值的平均值 |
| `Sum` | 计算数值之和 |
| `Minimum` | 取最小值 |
| `Maximum` | 取最大值 |
| `Approximate cardinality` | 估算唯一值数量 |
| `Exact cardinality` | 精确统计唯一值数量 |
| `Collect list` | 收集为列表，**保留重复** |
| `Collect set` | 收集为集合，**去重** |

- **聚合何时可选**：若链上每条 link 最多只到达一个对象，则聚合是可选的，可直接选择某个属性。
- **collection limit**：默认 **10**，最大可提到 **100**；对 `Collect set`，**先去重再施加限制**，因此限制的是返回的**不同值个数**而非考虑的总值数；该限制决定**返回的属性值个数**，不是被求值的值的个数——对已收集属性的过滤与排序运行在**完整值集合**上，因此对象可能命中的是未出现在返回列表中的值。
- 收集到的值可归约为单个代表值（指向 property reducers 文档，本地无该页）。

### 5.4 多跳（multi-hop）

- 派生属性支持**最多三层**链接对象跳转（例：`Department → Employee → Project`）。
- 配置方式：选第一个 link type → `Add linked object` 增加一层 → 从新连接的对象类型选下一个 link type → 最多三层。
- 每增加一次跳转都可能降低查询性能；官方建议用**最少的跳转**到达所需数据。
- **重要限制**：若需要从另一个派生属性派生值，应改为构建直接跳到源数据的 multi-hop 派生属性——**派生属性不能取自另一个派生属性**。

### 5.5 识别与限制

- 派生属性在 `Properties` tab 中与原生属性并列出现，带标记表示其值是**计算**而非存储的。
- 官方声明派生属性有跨平台的能力限制，包括对**主键、required properties、value types、显示格式化、以及使用 OSv1 索引的对象类型**的限制；完整清单在 derived properties limitations 页（**本地无该页**）。

---

## 6. Link type（链接类型）

### 6.1 定义

- 官方定义：**link type 是两个对象类型之间关系的 schema 定义**；一条 **link** 指同一本体内两个对象之间该关系的单个实例（link-types-overview）。
- 例：`Employee` ↔ `Company` 之间定义 `Employee → Employer` 关系；`Flight` ↔ `Aircraft` 之间定义 `Scheduled Flight → Assigned Aircraft` 关系。
- **允许自链接**：链接也可存在于同一类型的两个对象之间（例：`Employee` 与自身定义 `Direct Report ↔ Manager`）。
- **不支持跨本体链接**：不同 Ontology 中对象类型之间的链接不受支持；此场景建议使用共享 Ontology（shared Ontology）。

### 6.2 方向性（Directionality）——官方强调

- link type 是**双向的**：**始终有两个 side（侧）**，每侧对应它关联的两个对象类型之一。
- **每侧可独立遍历**，且**各自有自己的 display name 与 API name**（TSv1）。
- 例：`Flight ↔ Aircraft` 一个 link type 含 `Flight` 侧与 `Aircraft` 侧。代码中 `flight.assignedAircraft.get()` 遍历 `Aircraft` 侧取该航班被分配的飞机；`aircraft.flights.all()` 遍历 `Flight` 侧取该飞机被分配的航班。
- **不会隐式创建反向 link type**：单个 link type 已支持两个方向遍历，无需再分别定义 `Aircraft → Flight` 与 `Flight → Aircraft` 两个 link type 表示同一关系。
- 可在同一对对象类型之间定义**多个不同**的 link type，但每个代表一个**独立的关系**而非已有关系的反向（例：除表示被分配飞机的 `Flight ↔ Aircraft`，还可定义表示计划维修记录的第二个独立 `Flight ↔ Aircraft`）。**每个 link type 要求其两侧有唯一的 API name**，以便应用区分关系。

### 6.3 关系类型（3 种 join/storage 方式，三选一）

官方「Choose the relationship type」步骤提供三种：

| 关系类型（官方名称） | 支持的基数 | 官方说明 |
|---|---|---|
| **Object type foreign keys** | 支持 **"one-to-one"** 与 **"many-to-one"** 基数 | 可选择代表外键的属性以及对应对象的主键属性 |
| **Join table dataset** | 用于 **"many-to-many"** 基数 | 使用 join table 数据集来支撑链接 |
| **Backing object type** | 在 **many-to-one** 基数之上扩展 | 把对象类型作为链接类型的存储方案，提供一等公民支持 |

### 6.4 Cardinality（基数）官方取值与数据要求

官方在 create-link-type 中以 `Aircraft` 与 `Flight` 为例逐一说明：

| 取值（官方原样） | 官方含义 | 对数据/实现的要求 |
|---|---|---|
| **One-to-one cardinality** | 表示**一个 `Aircraft` 应当链接到单个 `Flight`**；官方明确：one-to-one 基数只是**预期关系的指示，不被强制（not enforced）** | 用 **Object type foreign keys** 方式定义：外键属性引用另一对象类型的主键属性，且两者属性类型必须匹配 |
| **One-to-many cardinality** | 表示**一个 `Aircraft` 可以链接到多个 `Flights`** | 文档未把该基数归入某一 join 选项（外键选项官方写的是 one-to-one 与 many-to-one，见 §13 不一致点） |
| **Many-to-one cardinality** | 表示**多个 `Aircraft` 可以链接到一个 `Flight`** | 用 **Object type foreign keys**；object-backed link type 是在 many-to-one 之上的扩展 |
| **Many-to-many cardinality** | 表示**一个 `Aircraft` 可以链接到多个 `Flights`，且一个 `Flight` 可以链接到多个 `Aircraft`** | **必须**用 **Join table dataset**：需选择包含两个对象类型主键**全部组合**的数据源；**many-to-many 需要 backing datasource，且只有它才允许用户编辑或 writeback 到该 link type** |

补充：link-type-metadata 从「每侧对象有 one 还是 many」的角度描述基数——例 `Employee → Employer` 中 `Employee` 侧基数为 `many`、`Company` 侧为 `one`；`Direct Report ↔ Manager` 中若直接下属可有多个经理、经理可有多个直接下属，则两侧基数均为 `many`。

### 6.5 三种方式的 link resources 配置细节

**A. Foreign key（外键）**

- 官方定义：**外键是某一对象类型上的属性，存储另一个对象类型主键的值**，表示两个对象类型之间的现实关系；概念类比关系型数据库中外键列引用另一表的主键列。
- 在 one-to-one 或 many-to-one 基数下，你需要定义外键属性与主键属性；**一个对象类型的外键属性必须引用另一对象类型的主键属性**。
- 示例：`Aircraft` 上 `Tail Number` 是主键；`Flight` 上 `Flight Tail Number` 是外键；当 `Aircraft` 的 `Tail Number` 匹配某 `Flight` 的 `Flight Tail Number` 时建立链接。
- 配置顺序：右侧下拉选**主键对象类型**（`Aircraft`）→ 左侧下拉选**外键对象类型**（`Flight`）→ 选择构成链接的属性（外键端选外键属性；主键端自动选中，因为**每个对象类型只有一个主键**）。
- **自动检测外键的条件**（满足则对话框自动选中）：① 外键匹配被链接对象类型的主键；② 两个对象的属性类型匹配。

**B. Join table dataset（连接表数据集）**

- 选择包含第一个对象类型主键与第二个对象类型主键**全部链接组合**的数据源。
- 配置：左侧选第一个对象类型（`Flight`）→ 右侧选第二个对象类型（`Aircraft`）→ 选择 join table 数据集（**必须含匹配两个对象类型主键的列**；**一列只能映射到一个主键**）→ 选择连接表数据源中哪些列映射到各被链接对象类型的主键。
- **`Generate join table` 选项**：可为新 link type 自动生成连接表——依据所选两个对象类型的主键创建具有正确 schema 的数据集，便于快速起步（已有用户编辑支撑的数据，或想以后再提供生产数据时尤其有用）。

**C. Backing object type（对象支撑链接）**

- 官方定义：object-backed link type **在 many-to-one 基数链接类型之上扩展**，为「把对象类型作为链接类型存储方案」提供一等公民支持；**允许在链接上附带额外元数据，并支持受限视图（restricted views）**。
- 示例：除 `Aircraft`、`Flight`，引入 `Flight Manifest` 对象类型作为中间桥梁；与 foreign key 或 dataset 支撑的链接不同，该 `Flight Manifest` 对象**可包含 `Pilot`、`First Mate` 等额外属性**，为链接提供附加元数据。
- **前置条件（必须先完成）**：

  1. 创建链接两侧的对象类型（`Aircraft`、`Flight`）；
  2. 创建把两个对象类型连接起来的 backing object type（`Flight Manifest`）；
  3. 创建每一侧到该 backing object type 的 **many-to-one** link type（`Aircraft ↔ Flight Manifest`、`Flight ↔ Flight Manifest`）。

- 创建时：选择代表目标 link type 的对象类型；**左侧与右侧对象代表将被链接的两个实体，中间对象作为中介，提供连接的附加元数据并支撑链接**；若左右对象与中间对象之间存在多条链接，用下拉菜单选择所需链接。
- **把既有链接转换为 object-backed link type** 的步骤：打开该链接 → 在 `Configuration` 区更新 join method 并选择 `Object type` → 在 `Update link type to object-backed link type` 对话框中选择 backing object type → 选择从链接边到 backing object 的 link type → 选择 `Update to object-backed`。（修改前须满足上述前置条件。）
- **使用范围**：object-backed link type 目前可在 **Object Explorer、Vertex、Workshop** 中查看；选择一条链接可查看其 backing object 的属性；**在 Vertex 中，链接标题会显示该链接 backing object 的标题**。

### 6.6 链接类型元数据完整清单

来源：[link-type-metadata.txt](../clean/object-link-types__link-type-metadata.txt) + [create-link-type.txt](../clean/object-link-types__create-link-type.txt) + [edit-link-types.txt](../clean/object-link-types__edit-link-types.txt)。

| 属性名（官方英文） | 中文含义 | 是否必填 | 取值范围 / 枚举 |
|---|---|---|---|
| **ID** | 链接类型的唯一标识符，主要在配置应用时引用该类型的链接 | 未在本地文件的强制清单中列出 | 例 `employee-employer` |
| **RID** | 自动生成的全局唯一资源标识，会出现在平台错误信息中 | 系统自动生成 | — |
| **Status** | 表示链接类型处于开发流程的哪个阶段 | 未列为必填；**默认 `experimental`** | `active` / `experimental` / `deprecated`；**active 的链接类型不能删除** |
| **Object types** | 通过该链接类型定义相关联的两个对象类型 | 必填 | 例 `Employee` 与 `Company` |
| **Cardinality** | 向应用指示该 link type 中每个对象类型是 one 还是 many | 配置项（随关系类型确定） | 每侧取值 `one` / `many`；完整基数枚举见 §6.4 |
| **Key** | 用于创建链接的属性或列 | **必填/必配** | one-to-one、one-to-many 下：一侧对象类型的属性（外键）引用另一侧的主键属性；many-to-many 下：一个含成对主键的表（join table），并需映射哪些列对应哪个对象类型的主键 |
| **Display name（每侧）** | 访问该类型链接时用户可见的名称；每侧各有一个 | **必填**（官方：为每一侧输入 display name） | 自由文本；一侧代表「链接**到**该对象类型」 |
| **Plural display name（每侧）** | 访问该类型链接、且存在多个被链接对象类型时显示的名称 | 未列为必填（示例中 `one` 端（Company）没有复数显示名） | 自由文本 |
| **API name（每侧）** | 代码中以编程方式引用链接类型时使用的名称；某侧的 API name 可用于返回该类型的对象 | **必填**（未填时按 display name 自动生成，可修改） | 首字符小写；仅字母数字；**同一对象类型关联的所有 link type 内唯一**；长度 1–100；**须 NFKC 规范化**；**不得是保留关键字** |
| **Visibility（每侧）** | 向应用指示该侧（指向该侧对象类型的链接）的展示显著程度 | 未列为必填；**默认 `normal`** | `normal` / `prominent` / `hidden` |
| **Type classes** | 供用户应用解释的附加元数据 | 未列为必填 | **本地文件未给出清单** |
| **Backing datasource / join table** | 支撑链接的数据源 | **many-to-many 基数必填**（many-to-many「requires a backing datasource」） | 数据源；**一个 datasource 只能支撑一个 link type**（见错误码） |
| **Foreign key** | 一侧对象类型上引用另一侧主键的属性 | one-to-one / many-to-one 下需要 | 必须引用另一对象类型的主键，且属性类型匹配 |

### 6.7 创建流程与 API 命名要求

**向导步骤**：Choose the relationship type → Define link resources → Define link type names → Save location（选项目后 `Submit`）→ Save change to ontology（回到 Ontology Manager 右上角 `Save`）。创建完成后**尚未保存**，必须 Save 才生效。

**入口**（三种）：右上角 `New > Link type`；左侧边栏 `Resources` 下 `Link types` → 右上角 `New link type`；在某个对象类型 `Overview` 页的 link type 图中选择 `Create new link type`。

**link type API name 必须满足**（官方原文要求）：

- 首字符小写、仅字母数字；
- 在**与同一对象类型关联的所有 link type** 中唯一；
- 长度 1–100；
- **NFKC 规范化**；
- 不是保留关键字。

**API name 用法示例**：若 `Aircraft` 侧的 API name 是 `assignedAircraft`，则 `Flight.assignedAircraft.get()` 会返回与这些 `Flight` 对象链接的 `Aircraft` 对象。

### 6.8 编辑链接类型与破坏性变更

**会注销/重新注册（或删除）链接类型 backing datasource 的变更**（reindex 期间该类型链接在用户应用中**不可用**）：

1. 更改 many-to-many 链接类型的 backing datasource
2. **更改链接类型的 cardinality**
3. **更改链接类型的外键**
4. 删除链接类型

**已启用 writeback 时的额外风险**：对**任何「曾经收到过编辑」**的支撑数据源列做 schema 变更（**包括列名与 base type 的变更**）也需要注销。同样地，Object Storage v1 **不会自动注销**，而是 **reindex 失败**；须撤销变更或手动注销+重新注册。

**编辑元数据**：

- **Status**：在链接类型面板顶部选择，下拉含 `deprecated`、`experimental`、`active`。
- **Key**：从下拉更改外键或 many-to-many 的列映射。约束：
  - many-to-many 下，支撑数据源中的列必须映射到对象类型的主键；**若对象类型主键属性的类型与链接类型支撑数据源中它所映射到的列类型不同，保存会被错误阻止**。
  - **其他任何基数**下，应用要求其中一个对象类型的 key **必须映射到该对象类型的主键**，以保证基数的「one」侧唯一。
- **API name**：可直接改；**active 状态不可改**。
- **Visibility**：从链接可见性列表勾选（prominent 会促使应用优先展示；hidden 不出现在用户应用中）。
- **Type classes**：可作为附加元数据应用（官方指向 type classes 清单，本地无）。
- 更换 backing datasource：`Datasources` 页 → 现有数据源旁的 `Select` 图标 → 选新数据源。**仅当新数据源与旧数据源 schema 相同时 key 才自动重映射**，否则须手工重映射。
- 删除链接类型：链接类型视图侧边栏右上角三点 → `Delete`，弹窗确认暂存删除；**保存后才生效，且会破坏引用该对象类型的视图或应用**；**active 状态不能删除**。

**官方错误码**：`Phonograph2:DatasetAndBranchAlreadyRegistered` —— 支撑该链接类型的数据源已在支撑本体内另一个链接类型，不能再次使用。

---

## 7. Shared property（共享属性）

- **官方定义**：shared property 是**可以在本体内多个对象类型上使用的属性**；共享属性使跨对象类型的数据建模保持一致，并**集中管理属性元数据**。
- **关键限定**：**属性元数据跨对象共享，但底层对象数据不共享**（"While property metadata is shared across objects, the underlying object data is not."）。
- 例：`Employee` 与 `Contractor` 都有 `start date`；通过建立一个 `start date` 共享属性供两者使用，可用一致的属性建模，并在一处更新 `start date` 元数据而非每个对象类型各改一次。
- **产生方式**：可直接创建；也可把对象类型上的既有属性**转换**为共享属性。
- 加入本体后，共享属性可在对象化数据（ontologizing your data）时用于对象类型，并以类似普通属性的方式编辑。
- **UI 标识**：对象上的共享属性名称旁有**地球图标（globe icon）**。
- 接口属性也可使用共享属性定义（interfaces 文档：interface properties can be defined locally on the interface（推荐） or using shared properties）。

---

## 8. Value types（值类型）

- **官方定义**：value types 是**围绕 field type 的语义包装（semantic wrappers）**，包含元数据与约束，可增强类型安全、提升表达力并提供额外上下文；它封装领域特定数据类型，并以**可在平台内复用**的方式实施数据校验。
- **与 field type / base type 的区别**：field types 与 base types 是**静态定义**的，用户不能创建新的 field type 或 base type；而 value types 在给定 **space** 的上下文中被定制，用户**可以动态创建** value types。
- **归属与可用范围**：
  - value types 关联到平台中的 **space**；**一个 space 只能容纳一个 ontology**；
  - **value types 只能在其定义所在的 space 内使用**；
  - **Default ontology 不可用 value types**。
- **设计意图**：dataset field types 与 property base types 反映编程语言中的原始类型，**与领域无关、不提供领域上下文**；value types 则捕获数据的上下文与语义、集中数据校验。用户直接从 value type 理解含义，而不依赖列名或属性描述等周边信息。
- **约束生效范围**：value types 会在 **Builder pipelines 与 ontology** 中对其数据施加校验约束，使数据集成者与本体管理者能在数据流与模型中确保语义类型正确。
- **示例**：定义 `email` value type，带正则约束，确保任何使用它的属性都表示合法邮箱地址；可跨多个对象类型与 pipelines 复用，无需为每个此类属性重复校验逻辑。
- **工程属性**：由于意图跨多个 pipelines 与对象类型复用，value types 是**受权限管理（permissioned）**的，并有**版本（versioned）**以处理破坏性与非破坏性编辑。
- 常用 value types（type-reference 举例）：email addresses、URLs、UUIDs、enumerations。

---

## 9. Object type groups（对象类型分组）

- **官方定义**：object type groups 是一种**分类原语**，帮助用户更好地搜索与探索本体；由本体 **owners 与 editors** 通过 Ontology Manager 创建与管理。
- **配置入口**：Ontology Manager 侧边栏的 groups 菜单；也可在对象类型 overview 页选择 `Edit groups` 直接为对象类型添加分组。
- **对象类型上的 Groups 操作**：从已有分组列表添加；输入名称新建分组；从对象类型移除分组。
- **搜索与发现**：分组可在 Ontology Manager 的 `Search` 栏与 `Search` 栏对话框中搜索；Ontology Manager 的对象类型表支持显示与按分组过滤；分组也展示在 Object Explorer 首页。
- **权限**：要查看对象类型分组，用户须对分组所在项目拥有 **`viewer` 权限**。
- **历史迁移（官方时点信息）**：
  - 自 **2024 年 5 月 22 日**起，本页描述的 `group` 原语**取代了旧的基于 tag 的分组系统**；多数情况下旧分组在该时间点被自动迁移，若需人工处理，本体 owner 会通过 **Upgrade Assistant intervention** 收到通知。
  - **分组可见性变化**：此前若某分组内所有对象类型对某用户都不可发现（例如因 backing dataset 的访问控制），该分组也对用户不可发现；**现在所有分组对任何能查看本体的用户都可发现**，以与其它本体原语的分组可见性对齐，提升治理的清晰与透明。
  - **部分可见分组的迁移**：对某用户不可发现的旧分组不符合自动迁移条件 → 通知 owner 人工处理；2024-05-22 起，无法安全迁移的旧分组在 Workshop、Object Explorer 等所有应用中对**运营用户隐藏**；为向后兼容，**旧分组的名称仍作为 type class 元数据存储在对象类型上**。owner 可继续在 Ontology Manager 中手工迁移：左下角 `Ontology Configuration` 菜单 → `Approve all Groups for migration`。
  - 官方另注明：Groups as labels in object type metadata **取代了此前在主键属性上添加 `oe_home_page_object_type_group` type class 的方法**，该旧方法**已不再可用**。

---

## 10. Interfaces（接口）

### 10.1 定义

- **官方定义**：interface 是一种**本体类型**，描述对象类型的**形状（shape）与能力（capabilities）**；允许对具有共同形状的对象类型做一致的建模与交互。
- 例：`Facility` 接口可含 `Facility Name` 与 `Location` 属性；`Facility` 可被 `Airport`、`Manufacturing Plant`、`Maintenance Hangar` 等对象类型实现，各实现者还可包含额外的类型专属属性。
- 价值：使用 `Facility` 接口后，工作流能**聚合地或单独地**与这三个对象类型交互，无需知道这些对象类型的具体细节；若随后引入新的实现 `Facility` 的对象类型，工作流**立即兼容，无需额外重构**。

### 10.2 组成与能力

- 一个接口由以下部分构成：

| 组成 | 说明 |
|---|---|
| **interface properties（接口属性）** | 可在接口上本地定义（**官方推荐**），或使用**共享属性**定义 |
| **link type constraints（链接类型约束）** | 接口构成之一 |
| **action type constraints（操作类型约束）** | 接口构成之一 |
| **metadata（接口元数据）** | 关于接口的元数据 |

- **一个接口可被多个对象类型实现**。
- **接口可扩展（extend）**：类比编程语言接口，可扩展一个接口创建子接口，子接口继承原接口属性，再添加更具体的新属性。
- **对象类型实现（implement）接口**：表示其符合该接口定义；**对象类型可实现多个接口**，用于不同工作流；**接口也可扩展多个其他接口**，包括本身已扩展其他接口的接口，因此属性可沿多层接口继承。

### 10.3 接口与对象类型的区别（官方对比）

| 维度 | Object types（对象类型） | Interfaces（接口） |
|---|---|---|
| 具体性 | **具体（concrete）** | **抽象（abstract）** |
| schema 来源 | 由共享或本地属性定义 | 由 interface properties 定义 |
| 数据支撑 | **由包含属性值的数据集支撑** | **不由数据集支撑** |
| 实例化 | 可实例化为 objects | **不能被直接实例化**，必须由某个具体对象类型实例化 |
| 视觉区分 | — | 平台中图标周围有**虚线（dashed lines）** |

### 10.4 权限

- 接口通过 **Ontology roles** 授权。

### 10.5 当前支持范围（官方分级）

| 状态 | 应用/服务 | 说明 |
|---|---|---|
| **已支持** | Ontology Manager | 定义、编辑、实现接口 |
| **已支持** | Marketplace | 打包与安装接口 |
| **已支持** | Functions | **TypeScript v2** |
| **部分支持** | Actions | 可定义 action 来创建、修改、删除或链接实现接口的对象；**interface action type constraints 处于 beta**，可用于定义实现接口的各类对象类型应具备的 action 能力 |
| **部分支持** | Object Set Service | 可按接口搜索与排序对象；**按接口聚合仍在开发中**；**接口链接类型支持仍在开发中** |
| **部分支持** | Ontology SDK | 把接口用作与实现对象类型交互的 API 层；**支持因语言而异**，目前支持 TypeScript，Java 与 Python 支持在开发中 |
| **部分支持** | Workshop | 可创建基于接口的对象集并在受支持的 widget 中使用接口属性；**widget 支持程度不一，部分 widget 会把基于接口的对象集当作基于对象类型的对象集处理** |
| **未支持（开发中）** | Functions | **TypeScript v1 与 Python** 函数尚不支持 |

- 入门动作：创建新接口或扩展既有接口 → 用形状合适的对象类型**实现**该接口 → 随本体演进**编辑**它。

---

## 11. 概念之间的包含 / 依赖 / 引用关系

### 11.1 包含（谁装谁）

```
Ontology（一个 space 一个）
├── Object type（对象类型）
│     ├── Property（本地属性，至少 1 个）
│     │     └── Base type（基类型，可为 struct → 含若干 field）
│     ├── Shared property（引用，非独占）
│     ├── Keys：Primary key（恰 1 个）/ Title key
│     ├── Backing datasource（0 或 1；无则纯 action 写入）
│     ├── Groups（0..n，分类标签）
│     └── Interfaces（0..n 实现关系）
├── Link type（链接类型）
│     └── 2 个 Side（每侧含 display name / plural display name / API name / visibility）
├── Action type
├── Interface（含 interface properties / link type constraints / action type constraints / metadata）
└── Object type group（分类原语，跨对象类型）
Space
└── Value type（属于 space，只能在该 space 内使用）
```

### 11.2 依赖与引用（谁能引用谁）

| 关系 | 说明 |
|---|---|
| Object type → Property | 对象类型**包含**属性；**每个对象类型至少一个属性**（必须有主键）；属性 ID 在同一对象类型内唯一 |
| Property → Base type | 每个属性有且仅有**一个** base type；决定可用操作与能否当 title/primary key |
| Property → Shared property | 普通属性可被转换为共享属性；共享属性可被**多个对象类型**使用；共享的只是元数据，数据不共享 |
| Object type → Backing datasource | 0 或 1 个；**一个 datasource 只能支撑一个对象类型**；不得含 MapType / StructType 列 |
| Object type → Title key / Primary key | 二者都指向该对象类型上的某个属性（须满足对应有效性）；**每个对象类型只有一个主键** |
| Link type → 2 个 Object type | 关联恰好两个对象类型（可为同一类型，即自链接）；**不支持跨 Ontology** |
| Link type → Property（经 FK） | one-to-one / many-to-one 下，一侧的 FK 属性**必须引用**另一侧的 primary key 属性，且类型匹配 |
| Link type → Join table dataset | many-to-many 下**必须**有 backing datasource，且列须映射到两侧对象类型的主键（一列只映射一个主键） |
| Object-backed link type → Object type ×3 + Link type ×2 | 依赖两侧对象类型、中间 backing object type，以及两侧到 backing object 的两个 many-to-one link type |
| Derived property → Link type 链 | 依赖 link type 链条（≤3 层）与末端属性；**不能依赖另一个派生属性** |
| Interface → Object type | 接口**不被数据集支撑**、不可实例化，只能被对象类型实现；对象类型可实现多个接口；接口可扩展多个接口 |
| Object type group ↔ Object type | 分组分类对象类型；对象类型可属于 0..n 个分组 |
| Value type → field type | 值类型是 field type 的语义包装；属于某个 space；只能在该 space 内使用；Default ontology 不可用 |

### 11.3 必填 vs 可选的速查

| 层级 | 必填 | 可选/默认 |
|---|---|---|
| 保存对象类型 | ID、Display name、Plural display name、Backing datasource（除非无数据源创建）、API name | Description、Aliases、Icon、Groups、Status（默认 experimental）、Visibility（默认 normal） |
| 保存对象类型（属性侧） | Property ID、Property display name、Backing column（除非仅通过 actions 填充）、Property API name、**Title key**、**Primary key** | Description、Status、Value formatting、Conditional formatting、Type classes、Render hints、Visibility（默认 normal） |
| 对象类型整体 | **至少一个属性**（因为要有主键） | 媒体等高级属性类型不能由向导生成，需退出向导后添加 |
| 无数据源创建对象类型 | 保存在项目中 + 配置 object security policy + 每个对象有唯一主键值 | — |
| 链接类型 | 两个对象类型、每侧 display name、每侧 API name、key（FK 或 join table 映射） | 每侧 plural display name、每侧 visibility（默认 normal）、Status（默认 experimental）、Type classes |
| many-to-many 链接类型 | **必须**有 backing datasource（join table） | — |
| 派生属性 | Source type = Linked objects、link type；链上存在可到达多对象的 link 时**必须**选聚合 | 聚合（当每条 link 至多到达一个对象时可选）、collection limit（默认 10，最大 100） |
| Struct 属性 | 至少一个字段；backing column 为 struct 类型列 | — |

---

## 12. 文档里出现但容易忽略的细节

**命名与 ID 规范**

1. 对象类型 **ID**：可含小写字母、数字、连字符；正文写「首字符**必须**是小写字母」，而同一页 `Valid ID checklist` 写「**Should start with a letter**」——两处措辞强度不同（见 §13）。
2. 属性 **ID**：可含**小写或大写**字母、数字、连字符、**下划线**；应以字母开头；同一对象类型内唯一（比对象类型 ID 宽松，多了大写与下划线）。
3. 对象类型 **API name**：PascalCase、首字符大写、仅字母数字、**跨所有对象类型唯一**、**1–100 字符**。
4. 属性 **API name**：camelCase、首字符小写、仅字母数字、**同一对象类型内唯一**、**1–100 字符**。
5. 链接类型**每侧** API name：首字符小写、仅字母数字、**在同一对象类型关联的所有 link type 内唯一**、1–100、**必须 NFKC 规范化**、不得为保留关键字。
6. **保留关键字**（不能用作 API name）：`ontology`、`object`、`property`、`link`、`relation`、`rid`、`primaryKey`、`typeId`、`ontologyObject`。
7. 新建对象类型与属性会**自动分配**由 display name 推断的 API name，之后可改。

**状态与可见性枚举（跨三类资源一致）**

8. **Status** 取值恒为三值：`active` / `experimental` / `deprecated`；**默认 `experimental`**（对象类型、属性、链接类型三者一致）。
9. **Visibility** 取值恒为三值：`normal` / `prominent` / `hidden`；**默认 `normal`**；`prominent` 会让应用优先展示，`hidden` 不出现在用户应用中。
10. **active 状态的硬约束**：对象型/链接型 **active 不能删除**；对象类型与链接类型 **active 时不能改 API name**；属性 **active 不能删除、不能改 API name**；**active 状态下不能更改对象类型的主键**。
11. 另有系统字段枚举：对象类型 **Index status** = `success` / `failed` / `not started`；**Writeback** = `enabled` / `disabled`。

**键与唯一性**

12. **每个对象类型只有一个主键**（create-link-type 明确说明主键端自动选中）。
13. 主键必须**唯一**且**确定性**；重复主键在 OSv2 会导致 Funnel batch pipeline 错误 → 构建失败，在 OSv1 会「看起来成功」但引起本体意外变化。
14. 主键**不推荐**用时间型（`Date`/`Timestamp`）与 `Boolean`/`Byte`/`Long`；`Float`/`Double`/`Decimal`/`Vector`/`Array`/`Struct`/`Geoshape`/`Marking`/媒体类/时序类/Attachment **不能作主键**。
15. **编辑永久绑定在主键值上**；更换主键会提示删除所有既有编辑。
16. **对象类型 ID 创建后不可编辑**。

**数据源约束**

17. **一个 datasource 只能支撑一个对象类型**（错误 `Phonograph2:DatasetAndBranchAlreadyRegistered`）；同理**一个 datasource 只能支撑一个 link type**（同名错误）。
18. backing datasource **不得含 `MapType` 或 `StructType` 列**（create-object-type）——但 struct 属性官方又说「由单个 struct 类型列支撑」、「目前只能从数据集与受限视图创建」（见 §13 张力点）。
19. **移除 backing datasource 会把原先映射的每个属性变为 edit-only**，值改由 actions 提供；且**仅在对象类型保存于项目中时**才能移除数据源。
20. 更换 backing datasource 时，**只有 schema 相同时**属性（对象类型）或 key（链接类型）才自动重映射。
21. 数据源支撑类型的对象权限**继承自 backing datasource 位置**，因此不需要配置 object security policy；无数据源创建则**必须**配置。

**破坏性变更（易漏）**

22. 对象类型的三类变更会注销/重注册数据源：**换数据源、换主键、删除对象类型**；链接类型为：**换 many-to-many 的支撑数据源、改 cardinality、改外键、删除链接类型**。
23. 启用 writeback 后，对**「曾经收到过编辑」**的属性/列做 schema 变更（属性看 **ID 与 base type**；链接列看 **列名与 base type**）**也需要注销**——注意是「曾经收到过」而非「当前正在收到」。
24. **不需要**注销的变更：display name、title key、render hints、type classes、visibility；以及删除/改**从未收到编辑**的字段。
25. Object Storage v1 **不会自动注销**，而是让 **reindex 失败**；必须撤销变更或在 `Phonograph` 面板手动注销+重新注册。
26. `Create`（或 `Submit`）**只暂存不保存**；必须回到 Ontology Manager 右上角 `Save` 才写入本体。

**属性与类型细节**

27. `Array` 属性**不能含 null 元素**；内层类型若不是有效 title property，则该 Array 也不能作 title property；**OSv2 不支持嵌套数组**；`Vector` 与 `Time series` **不能用于数组**。
28. `Struct` 不能套 struct、字段不能是数组、**必须至少一个字段**；**OSv1 不支持 struct**；struct 查询按字段独立求值（ElasticSearch object field 语义），数组场景可能「跨元素拼凑」命中。
29. **受限支持类型**：`byte`/`float`/`short` **不能用于 action types**；`vector` 只能 **KNN** 查询，**最大维度 2048**。
30. `Boolean` 作主键会把对象类型**限制为两个对象实例**；`Byte` 只能在 Actions 中通过 `Integer` 参数赋值；`Long` 大于 **1e15** 在 JavaScript 中有表示问题。
31. `Geopoint` 存储为逗号分隔字符串 `latitude,longitude`（例 `57.64911,10.40744`）。
32. **`Map` 与 `Binary` 不是合法 base type**（所有 field type 中唯二例外）。
33. 媒体引用属性**必须**在对象类型 `Capabilities` tab 配置**一个或多个 media sources**；多个时需指定 `Upload destination`。
34. 改属性 base type 后**必须同步修改相关 Action 的 expected type**；改属性元数据后**必须 re-index**。
35. **每个对象类型至少一个属性**，理由官方明确：需要主键。
36. 媒体等需要高级配置的属性类型**不能在创建向导中生成**。

**链接类型细节**

37. link type **天然双向**，无需（也不应）为反方向再定义第二个；同一对对象类型间可有**多个独立** link type，但每侧 API name 必须唯一。
38. **one-to-one 基数不被强制**，只是意图指示。
39. 链接类型自动检测外键的两个条件：**FK 匹配被链接对象类型的主键** + **两个对象的属性类型匹配**。
40. many-to-many 的 join table 中，**一列只能映射到一个主键**；若列类型与对象类型主键属性类型不一致，**保存会被错误阻止**。
41. 非 many-to-many 基数下，应用要求**其中一个对象类型的 key 必须映射到该对象类型的主键**，以保证「one」侧的唯-一性。
42. **只有 many-to-many 需要 backing datasource**，且**只有它支持用户编辑 / writeback**。
43. `Generate join table` 可自动按两侧主键生成正确 schema 的连接表。
44. object-backed link type 需先建好 **两侧对象类型 + 中间 backing object type + 两条 many-to-one 链接**；Vertex 中该链接标题显示**backing object 的标题**；支持 **restricted views**。
45. 链接类型的每侧可有独立 visibility，且 `one` 端可以没有 plural display name。

**接口、分组、值类型、派生属性细节**

46. 接口**抽象、无数据集支撑、不可直接实例化**，只由对象类型实例化；图标有**虚线**；通过 **Ontology roles** 授权。
47. 接口属性官方**推荐本地定义**，也可用共享属性；接口可扩展多个接口（多层继承），对象类型可实现多个接口。
48. 分组的旧机制：**`oe_home_page_object_type_group` type class 方法已不可用**；2024-05-22 起 group 原语取代 tag 体系；未能安全迁移的旧分组**名称仍作为 type class 元数据**保留在对象类型上。
49. 查看分组需项目 **`viewer` 权限**，但**所有分组对任何能查看本体的用户都可发现**。
50. value types **属于 space**（一个 space 仅一个 ontology）、**只能在该 space 内使用**、**Default ontology 不可用**；且是**受权限管理 + 有版本**的。
51. 派生属性是 **beta**；**最多三层**链接跳转；**不能取自另一个派生属性**；`Collect set` **先去重再限流**；collection limit **默认 10 / 最大 100**；过滤与排序基于**完整值集合**而非返回列表。

---

## 13. 本地文件里没查到 / 语焉不详

以下内容在指定的 19 个文件中**没有**或**只有间接片段**，不做推测；如需补全，需要 `clean/` 中并不存在的对应页面（目录已确认无同主题文件）。

### 13.1 任务里点名、但指定文件中查不到的字段

| 缺失项 | 情况说明 |
|---|---|
| **Object Type 的 `Type classes`** | [object-type-metadata.txt](../clean/object-link-types__object-type-metadata.txt) 的元数据清单**未列出**对象类型的 type classes；type classes 只作为**属性**元数据与**链接类型**元数据条目出现。create-object-type 中仅作为历史遗留提到主键属性上的 `oe_home_page_object_type_group` type class 已废弃。 |
| **Object Type 的 `Render hints`** | 同上，对象类型元数据清单**未列出**；render hints 只在**属性**元数据中出现。 |
| **Object Type 的 `Groups` 之外的分类字段** | 无。 |
| **Property 的 `Required`（必填属性）** | 19 个文件中**没有**任何名为 `Required` 的属性配置项。仅在派生属性页出现「restrictions on ... **required properties**」的措辞（属于派生属性能力限制），未给出定义、枚举或配置位置。 |
| **Property 的 `Unique`（唯一约束）** | 文件中**没有** `Unique` 配置项。唯一性只以两种形式出现：主键值必须唯一；属性 ID / API name 的命名唯一性。 |
| **Property 的 `Edit-only`** | **没有专门页面**（clean 目录下无 `edit-only-properties` 文件），也没有独立字段条目。仅有间接表述：① 移除 backing datasource 后原先映射的每个属性**变为 edit-only 属性**，值由 actions 填充；② 必填字段中「**Backing column，除非该属性仅通过 actions 填充**」。edit-only 的完整配置项、开关位置、约束均未说明。 |
| **`Render hints` 完整清单** | 未给出。仅出现两个例子 **`searchable`、`sortable`**（可取消勾选以提升 reindex 性能），以及「许多 render hints 会影响 reindex 性能」的定性说明。 |
| **`Type classes` 完整清单** | 未给出。仅出现一个历史值 `oe_home_page_object_type_group`（已废弃）。 |

### 13.2 其它语焉不详处

| 主题 | 缺口 |
|---|---|
| **Status 完整语义** | 三个枚举值已知，但「何时必须用 active」「active 之外还有哪些强约束」等完整规则分散在 create/edit/metadata 页，**没有 statuses 专页**（clean 目录无该文件），因此状态间的迁移规则、对 reindex/权限的影响未见全貌。 |
| **Writeback 数据集配置** | 只说明概念（把用户编辑持久化到持久数据集）与 `enabled`/`disabled`，**未给出 writeback 的字段清单与配置步骤**。 |
| **Object Storage v1 与 v2 差异全貌** | 仅零散出现（OSv1 不支持该向导的 generate actions 与无数据源创建选项、不支持 struct、v2 不支持嵌套数组、重复主键行为不同），**没有系统对比页**。 |
| **对象类型 / 属性 / 链接类型的「验证要求」** | 三页元数据参考都写「Learn more about ... **validation requirements**」，但**对应验证要求页不在本地**；本地只有可拼凑的必填清单与 ID/API name 校验规则。 |
| **API name 与 ID 的校验规则存在两套措辞** | create-object-type 同一页内：正文 API name 要求「仅字母数字」，troubleshooting 章则写「仅字母数字**与下划线**」，且属性 API name 还要「**Be valid Unicode**」；对象类型 ID 正文写「首字符**必须**是小写字母」，检查单写「**Should** start with a letter / should start with a letter」。官方文本自身不一致，笔记两处均原样保留，未做取舍。 |
| **外键支持哪些基数，两处不一致** | create-link-type 的 `Object type foreign keys` 写「支持 **one-to-one** 与 **many-to-one**」；而同页 `Define link resources` 的 foreign key 小节，以及 link-type-metadata 的 `Key` 条目，都写「在 **one-to-one 或 one-to-many** 基数下，一侧属性（外键）引用另一侧主键」。**one-to-many 是否可用外键方式、many-to-one 是否算作 one-to-many 的镜像，文档未统一说明。** |
| **基数与 join 方式的完整组合矩阵** | 文档分别叙述三种关系类型各自支持的基数，**未给出完整矩阵**（尤其：one-to-many 应该用哪种关系类型；many-to-one 与 one-to-many 是否只是视角差异）。 |
| **对象类型 backing datasource 与 struct 列的矛盾** | create-object-type 明确「backing datasource 不得包含 MapType 或 StructType 列」；structs-overview 与 base-types 又说 struct 属性由「单个 struct 类型列」支撑，且 struct「目前只能从数据集与受限视图创建」。两者适用边界（是主数据源整体限制 vs struct 属性专用列例外）**文档未解释**。 |
| **`Phonograph2:DatasetAndBranchAlreadyRegistered` 的链接类型版本** | create-link-type 的错误小节只说明「该数据源已在支撑另一个 link type」，未说明是否存在与对象类型共享数据源的额外限制。 |
| **Value types 的字段清单与创建/使用流程** | 本地只有 overview（定义、space 归属、权限与版本化），**create-value-type 与「在属性上使用值类型」两页不在本地**，因此值类型的元数据字段、约束类型枚举均无。 |
| **Shared property 的创建与转换流程** | 本地只有 overview（定义、元数据共享/数据不共享、地球图标），**创建共享属性与把既有属性转换为共享属性的页面不在本地**，字段清单亦无。 |
| **Structs 的创建页与 main fields** | structs-overview 提到「create the struct property」与「Designate struct main fields」，但**对应页面不在本地**，因此 main field 的定义与配置项缺失。 |
| **Interfaces 的创建 / 扩展 / 实现细节** | 本地只有 overview，**create/extend/implement/edit 接口的页面不在本地**，因此接口的元数据字段清单、link type constraints 与 action type constraints 的具体配置项缺失。 |
| **派生属性的完整聚合参考与限制清单** | 本地只有配置页（含 9 种聚合与 collection limit、三层跳转），**derived properties reference 与 derived properties limitations 两页不在本地**，因此「哪些源属性类型可被哪些聚合接受」「对主键/必填属性/value types/OSv1 的完整限制」均无。 |
| **Property reducers（属性归约器）** | base-types 与 derived-properties 均指向 property reducers 页（如「collected values 可归约为单个代表值」），**该页不在本地**，归约器清单缺失。 |
| **Conditional formatting 与 Value formatting 的具体选项** | 只给出概念与「数值 / 日期时间 / 用户 ID / 资源 ID 格式化」的分档，**具体格式化器与条件规则的配置项未列出**（对应专页不在本地）。 |
| **Object type 的 Render hints / type classes 在 UI 的可见位置** | create-object-type 的向导元数据步骤只列 Icon / Name / Plural name / Description / Groups；对象类型层面的 render hints 与 type classes 究竟是否存在、在何处配置，**指定文件无法回答**。 |
| **链接类型的 plural display name 何时必填** | metadata 页说「one 端没有复数显示名（因为每个员工只能有一个公司）」，但**未给出规则表述**（是否凡 `many` 侧才需要）。 |
| **Groups 与 Interface 的 Marketplace / 权限细节** | 仅提到分组需 `viewer`、接口用 Ontology roles，**具体角色清单不在本地**。 |
