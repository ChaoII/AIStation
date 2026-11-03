# 问数（Text-to-SQL）业界实现方案调研

> 目的：我们最近三次"往 prompt 里加更详细的中文元数据"（资产描述、本体属性说明、枚举取值）
> 配对实测都是**零收益**。本文梳理同行到底怎么做的，用来判断我们的方向错在哪。
>
> 结论先行：**它们都在做减法（少表、少列、结构化语义），没有一家靠"堆描述"取胜。**
>
> 调研时间：2026-11 ｜ 来源均为官方文档（链接见文末）。

---

## 一、五条共性（先看这个）

1. **限制上下文的规模是产品设计，不是优化项。**
   Genie 限 50 张表、知识库 200 条；Snowflake 要求"从一个简单星型模型开始"。
   没有任何一家把几百张表的全部列塞给模型。

2. **语义放进"结构"，不放进散文。**
   Snowflake 用 semantic view（facts / metrics / dimensions / relationships）；
   Genie 用 SQL expression（measure / filter / field + 同义词）；
   Palantir 用 ontology（object / property / link / action）。
   同一件事在三家都是**可校验的结构化定义**，而不是"这段表是干嘛的"。

3. **示例 SQL（few-shot）是性价比最高的语义载体。**
   Genie 把 example queries 列为 Recommended，并支持参数化 + "verified answer"；
   Palantir 用 functions/actions 固化业务逻辑。

4. **值字典（entity matching）是单独的机制，不是靠描述。**
   Genie 对低基数列维护"取值清单"（最多 120 列、每列 1024 个值），
   专门解决"用户说 Florida，库里存 FL"这类问题。

5. **按需取 schema，而不是先塞满。**
   Snowflake/Genie 都把语义视图/agent 当作**工具**挂给 LLM；
   Palantir 的 OAG 走"检索 → 组装上下文 → 生成"。

---

## 二、Databricks Genie（原 Genie Spaces）

### 2.1 结构

一个 Genie Agent = **数据源 + 指令 + 示例 + 知识库**四件套：

| 组成 | 上限 | 说明 |
|---|---|---|
| 数据源（表/视图/metric view） | **50 张** | 只能查挂上去的，挂不上的即使指令里提到也不会查 |
| Instructions | **100 条** | 每条 example SQL / SQL 函数 / 整段通用指令各算 1 条 |
| Knowledge store snippets | **200 条** | 表描述、join 关系、SQL 表达式共享这个额度 |

### 2.2 关键机制（值得照抄的）

- **示例 SQL**：给"用户最自然的问法" + 对应 SQL，可参数化（`:parameter`）；
  命中时直接复用 → 界面上标成 **verified answer**。
- **SQL 表达式**（measure / filter / field）：把 KPI 写成 SQL 片段 + 同义词。
  官方明确对比："定义成 SQL 表达式比写文字指令更稳定，因为 Genie 会**原样套用**，
  而不是从自然语言里再解释一遍。"
- **知识库**：表/列描述、列同义词、隐藏列、join 关系。
- **Prompt matching**：
  - *Format assistance*：自动采样代表值（理解格式）；
  - *Entity matching*：对低基数列维护值字典（≤120 列 × ≤1024 值），
    解决"Florida vs FL"。
- **知识挖掘**：从作者点赞/下载的查询里自动建议新的 measure / join。

### 2.3 权限

计算用作者的仓库凭证，**数据访问永远按终端用户自己的 Unity Catalog 权限**评估；
行过滤/列掩码对每个人自动生效。

---

## 三、Snowflake：Semantic Views + Cortex Analyst

### 3.1 核心对象

Semantic View 是**库内对象**（不是 prompt 里的文字），包含：

- **Logical tables**：对应业务实体（customers / orders / suppliers）；
- **Facts**：行级数值（"多少"），构造 metric 的原料；
- **Metrics**：聚合后的指标（`SUM(gross_revenue * (1 - discount))`）；
- **Dimensions**：分类维度（日期、品类、地区）；
- **Relationships**：表间 join 定义。

### 3.2 为什么这样做（官方原话的意思）

> 业务说"净收入"，库里叫 `amt_ttl_pre_dsc`。语义视图把"业务叫法 → 物理列 + 正确聚合"
> 固化成**单一权威定义**，避免几十份报表各算各的。

### 3.3 使用方式

- Cortex Analyst（REST API）或 Cortex Agents **把语义视图当工具**挂上去；
- 也支持 YAML 导入（可从 Tableau / Power BI 迁移），有校验规则；
- 官方建议：**从一个简单星型模型开始**。

---

## 四、Palantir Foundry：Ontology + AIP

### 4.1 两层

- **语义层（objects / properties / links）**：把数据集映射成"现实世界对象"
  （设备、订单、交易），带富元数据与细粒度治理；
- **动能层（action types / functions）**：变更（动作）与业务逻辑（函数），
  动作有参数、规则、提交条件、副作用、审计。

另有 **interfaces**（对象的多态形状）、**value types**（带约束的值类型，
如"金额"必须非负）、**object views**（可复用的对象视图）。

### 4.2 与 LLM 的结合（OAG，Ontology-Augmented Generation）

Palantir 的路线是 **检索 → 用本体组装上下文 → 生成**：
先从本体里确定"用户说的是哪个对象/属性/关系/动作"，再把这些**结构化定义**
交给模型，而不是把整库 schema 交给它。官方文档里 OAG 单独成章
（`/docs/foundry/ontology/ontology-augmented-generation/`）。

### 4.3 对我们的启示

我们的"本体对象 + 属性 + 关系 + 动作"这套建模**方向是对的**，
但 Palantir 的本体是**检索与执行的入口**，不是 prompt 的填充物。

---

## 五、学术界的共识：schema linking 才是关键

Text-to-SQL 这条线的公开结论（RESDSQL、DIN-SQL、MAC-SQL 等一脉）：

1. **先做 schema linking**：从问题里判断"会用到哪几张表、哪几列"，
   再生成 SQL；直接给全量 schema 是公认的劣化项（长上下文 + 无关列干扰）。
2. **分解 + 自一致性**：先判断题型（单表聚合 / 多表 / 嵌套），再生成；
   多候选取多数（我们已有 `self_consistency_n` 旋钮）。
3. **执行反馈**：跑一遍看结果是否合理，不合理带错因重试
   （我们已有 `empty_self_correct` + 结果自校验）。
4. **值匹配**：把用户口语词映射到库里的枚举值（对应 Genie 的 entity matching）。

> 注：以上是对该领域公开结论的概括，未逐篇核对具体数字；
> 需要引用数字时应回原论文。

---

## 六、横向对比

| 维度 | Databricks Genie | Snowflake Semantic View | Palantir Ontology | 我们（现状） |
|---|---|---|---|---|
| 上下文规模 | ≤50 表 | 星型模型起步 | 按需检索对象 | **12 表 × ~40 列 ≈ 480 列** |
| 语义载体 | 示例 SQL + 指令 + SQL 表达式 | facts/metrics/dimensions（库内对象） | 对象/属性/关系/动作 | prompt 文字 + 指标模板 |
| 值字典 | entity matching（≤120 列） | 维度取值 | value types | 有实现，**默认关**（实测无收益） |
| 列裁剪 | 支持隐藏列 | 语义视图只暴露必要列 | 属性按对象组织 | **无**（本次实验） |
| 示例 | 重点推荐，可参数化 | 无独立示例机制 | 无 | 76 条 few-shot，已接入 |
| 权限 | 用户自己的 UC 权限 + 行/列掩码 | 视图级 | 对象/行/列策略 | ABAC + 字段 ACL，已接入 |

---

## 七、对照我们自己的实测

| 我们的动作 | 实测结果 | 与同行的对照 |
|---|---|---|
| 资产描述注入 prompt | 无收益 | 同行也不靠表描述，靠**示例 + 结构化表达式** |
| 本体属性描述注入 | 无收益（1228 列独有信息） | 同行把属性放进**对象/维度**，不是散文；且只给相关对象 |
| 枚举取值注入 | 无收益 | 方向对（对应 entity matching），但我们只做"提示"、没做"匹配纠错"，且默认关 |
| 召回开关（关掉） | **-26pp，召回率 0.87→0.18** | 一致：检索质量是第一决定因素 |
| 快路径白名单 | 修掉 4 类抢答 | 一致：能确定性回答的走模板（metric view / SQL expression） |

**最关键的差距**：我们给 480 个列名，答案只用 1 表 2 列（实测中位数）。
同行在这个位置做的是"**先裁剪**"，我们做的是"**先铺满，再指望模型忽略**"。

---

## 八、我们该抄什么、不该抄什么

### 该抄

1. **列裁剪 + 表数上限**（Genie 的"隐藏列"、Snowflake 的"只暴露必要列"）——
   本次实验正是在验证这个（`schema_column_prune_enabled` / `recall_top_k`）。
2. **把可确定回答的问题做成结构化定义**（metric view / SQL expression）——
   我们已经有一部分（指标模板 161 条，78 条绑定本体），应继续扩大覆盖面，
   而不是让 NL2SQL 猜。
3. **示例 SQL 继续投入**（Genie 把它列为 Recommended）——
   我们 76 条 few-shot 已在用，可以按"错题沉淀"继续补（已有 `eval_curate`）。
4. **值字典做成"匹配纠错"而非"提示"**：查出与用户词最接近的库内值，
   直接替换/建议，而不是把 8 个值列在 prompt 里让模型自己挑。

### 不该抄

1. **不要靠表/列描述提升准确率**——三家都没有这么做，我们实测也没用；
2. **不要把所有列都列出来**——这是当前 prompt 84% 的体积来源；
3. **不要用文字指令表达业务口径**——Genie 官方明确说 SQL 表达式比文字更稳。

---

## 九、参考链接

- Databricks Genie Agents（创建与配置）：
  https://docs.databricks.com/aws/en/genie-agents/set-up
- Databricks Genie Agents（调优：示例、指令、知识库、entity matching）：
  https://docs.databricks.com/aws/en/genie-agents/tune-quality
- Snowflake Semantic Views（概念与为什么）：
  https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst/semantic-model-spec
- Palantir Foundry Ontology（对象/关系/动作）：
  https://www.palantir.com/docs/foundry/ontology/overview
- Palantir OAG（Ontology-Augmented Generation）：
  https://www.palantir.com/docs/foundry/ontology/ontology-augmented-generation/
