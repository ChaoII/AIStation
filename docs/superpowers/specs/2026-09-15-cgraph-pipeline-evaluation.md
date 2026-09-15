# ModelDeploy Pipeline 引入 CGraph 可行性评估

- 日期：2026-09-15
- 评估对象：`E:\CLionProjects\ModelDeploy\application\pipeline.cpp / pipeline_manager.cpp / infer_group.cpp`
- 备选：`ChunelFeng/CGraph`（v3.3.0，2026-08-22）
- 结论：**不建议整体替换**；**建议**在「单相机多模型子图」与「离线/近线批处理」这两类场景引入，且必须先做 POC 基准。

---

## 1. CGraph 事实核查

| 维度 | 事实 |
|------|------|
| 许可 | **MIT**（`LICENSE`，Copyright (c) 2026 Chunel Feng）→ 满足本项目"宽松许可"门槛 |
| 依赖 | **零第三方依赖**，纯 C++11 标准库 |
| 平台 | macOS / Linux / Windows / Android（CI: CMake4Win/Linux/Mac + CodeQL） |
| 活跃度 | 2.3k star / 390 fork；v3.2.5（2026-08-15）、v3.3.0（2026-08-22）；issue 仍有作者响应（#605 2026-08） |
| 能力 | `GPipeline` 调度 eDAG；`GNode`（继承实现 `run()` + 声明依赖）；`GGroup/Cluster/Region`（条件、循环、并发）；`GParam`（类型化参数、trace）；`GMessage`（**跨 pipeline** 发布订阅）；`GEvent`、`GAspect`（切面）、`GDaemon`（定时）、`GSome`；stage（节点间同步）；暂停/恢复/超时；拓扑与静态执行（含微任务）；lite 运行模式；graphviz 可视化；perf 分析；自带线程池（任务盗取 + 自动扩容） |
| 生态 | Python（`pycgraph`）、C#/Java/Go 端口、`CGraph-lite`（单头文件、接口兼容） |
| 引入成本 | 低：可作为 `third_party/` 子目录或 `FetchContent`（项目已有 paho.mqtt.c 的 FetchContent 先例） |

## 2. 现状 Pipeline 架构（事实）

```
VideoSource(解码, SDK 异步 + 缓冲池)
  → 有界队列 det_queue_（max 3，满则丢最旧 ⟶ 实时背压）
  → 单检测线程 detect_loop()：
        InferGroup::run_models(帧)     // 逐个模型串行；per-model interval 跳帧复用上次结果；ROI crop
        → trackers_（按 label_id 分组 ByteTracker，IoU 贪心回填 track_id）
        → DrawEngine（NV12 就地/回环，或 CPU 绘制）
        → VideoSink(编码, SDK 异步)
        → detection_sink_（事件装配 → EventBus ⟶ Agent 上报）
```

关键事实：

- **单线程关键路径**：`det+track+draw+encode < 40ms` 才能到 25fps（`pipeline.hpp:30` 注释明确这是设计目标）。
- **模型是串行的**：`InferGroup::run_models` 顺序遍历 `entries_`（`infer_group.cpp`），没有分支并行。
- **背压语义**是"丢最旧帧保最新"（`det_queue_`），不是阻塞队列。
- **多相机 = 多 Pipeline**，各自独立线程（`PipelineManager`）。
- 已有大量踩坑修复：4 处 SDK CPU NV12→BGR 越界崩溃、LPR det 框清零、tracking 双源/跨类、sink 合并条件等。
- 硬约束：`application/surveillance` 不得改动。

## 3. 契合点（CGraph 真正能帮上的地方）

1. **单相机多模型异构子图**（最契合）
   当模型增多且依赖变复杂时（如 `det → 按框 crop → 并行 [cls 属性, ocr 文本, lpr 车牌, face rec] → 合并 → track → draw`），CGraph 的 `GNode` 依赖 + 非依赖并发 + `GParam` 传参正是这个形状；现在是**手写串行**。收益 = 用满多核、缩短单帧延迟、模型组合可配置化。
2. **按任务配置动态构图**
   `TaskConfig.models[]` 已经描述了"这个任务要哪些模型"；CGraph 可在任务启动时按配置注册节点（拓扑在建图时确定，符合 CGraph 的静态图模型），避免为每种场景写死 pipeline 代码。
3. **运维能力白送**
   per-element 超时、暂停/恢复、perf 分析、graphviz 拓扑导出、`GAspect` 横切（打点/降级）——这些现在都要自己写。
4. **`GDaemon` + `GMessage`**：定时任务（快照/心跳/清理）与**跨 pipeline 通信**（如跨相机聚合，SP6-a 的天然底座）。
5. **离线/近线批处理**：对"吞吐优先、延迟不敏感"的分析任务（录像回溯、批量抽帧推理），CGraph 的并发调度显著优于当前串行实现。

## 4. 不契合点与风险（关键）

| # | 风险 | 说明 |
|---|------|------|
| 1 | **每帧 `process()` 的调度开销** | CGraph 以"一次 DAG 运行"为单位；25fps × N 相机 = 高频调度。虽有静态执行/lite 模式，但**必须实测**，否则可能吃掉 <40ms 预算。 |
| 2 | **线程模型冲突** | 每条 `GPipeline` 自带线程池；当前"每相机一 Pipeline 一线程"若直译成"每相机一 GPipeline"，会造成线程超订（8 相机 × 池）。需要改为"单 GPipeline + 多相机 Group"或自管线程。 |
| 3 | **延迟路径上的跨线程交接** | 现设计刻意让 det/track/draw/encode 在**同一线程**完成以免同步开销；CGraph 的并发节点意味着跨线程传递 `ImageData`（设备 NV12/BGR + 池化）——要么拷贝，要么传 `shared_ptr`，都要仔细设计，否则延迟与内存双输。 |
| 4 | **背压语义不匹配** | CGraph 的 message/queue 是通用阻塞/非阻塞模型，**没有内置"丢最旧"**；实时保新的背压需自行实现，否则延迟漂移。 |
| 5 | **回归风险集中在已修复区** | NV12 越界、sink 合并、track_id 回填等修复都在关键路径上；整体重写等于把这些坑重踩一遍。 |
| 6 | **确定性与可测性** | 现有多线程/单线程边界清晰、Catch2 用例覆盖充分；引入池化并发会带来非确定性，测试需重写（如引入帧级同步点）。 |
| 7 | **Batching/多相机共享** | CGraph 不天然支持"跨相机组 batch 推理"这类吞吐优化（当前也不支持，但若未来要做，CGraph 不直接帮忙）。 |
| 8 | **自研可控性** | 当前代码量不大（pipeline 554 / infer_group 158 / manager 483 行），问题域明确；引入框架换来的是"配置能力"而非"少写代码"。 |

## 5. 备选对比

| 方案 | 许可 | 适合 | 不适合 | 结论 |
|------|------|------|--------|------|
| **CGraph** | MIT | 可配置 DAG、异构分支、跨 pipeline 消息、运维特性（超时/暂停/perf/可视化）、daemon 定时 | 超低延迟逐帧热路径、需要精细背压 | 按场景引入（见 §6） |
| **Taskflow** | MIT | 通用任务并行、header-only、生态大（10k+ star）、`tf::Pipeline`/`tf::Taskflow` 简单直接 | 无 GParam/GMessage 这类领域设施，跨图通信要自建 | 若只需"并行跑分支"，Taskflow 更轻 |
| **Intel TBB Flow Graph** | Apache-2.0 | 工业级流图、带缓冲节点与背压原语（`buffer_node`/`sequencer`/`limiter_node`） | 依赖重、Windows 部署体积大 | 背压/限流需求强时可考虑 |
| **维持现状（自研）** | — | 关键路径可控、延迟可预测、零新增依赖 | 模型组合越复杂，`InferGroup`/`Pipeline` 越易膨胀 | **默认选项** |

> 值得注意：TBB 的 `limiter_node`+`buffer_node` 恰好能表达"丢最旧"背压，若目标是**流式低延迟**，TBB 比 CGraph 更对口；CGraph 的强项在**图结构的可配置性与运维设施**。

## 6. 建议路线（分阶段，含kill开关）

**阶段 0（1-2 天，零风险）**：基准与对照组
- 用现有 `Pipeline` 打点（已有 `PerfStats`）采集：单帧 `det/track/draw/encode` 分段耗时、各模型耗时、8 相机并发下的 CPU 占用与帧率。
- 写一个**独立的** CGraph 微基准（不入主工程）：N 个假节点模拟模型耗时，测 `process()` 每帧调度开销与并发收益，对比 Taskflow。**此步骤决定后续是否继续。**

**阶段 1（POC，隔离目录）**：把「单相机多模型」移植为 CGraph 子图
- 在 `application/third_party/CGraph`（或 CMake FetchContent）引入；新写 `pipeline_cgraph.cpp`，**不改** 现有 `pipeline.cpp`；用同一个 `TaskConfig` 驱动构图。
- 验收：功能等价（同视频同模型，检测/跟踪/事件字节级一致）+ 单帧延迟不劣化 >10% + 多模型场景延迟下降。
- **kill 开关**：若每帧调度开销 > 预算的 10%，停止。

**阶段 2（选择性落地）**：
- 落地范围限定为：**≥3 个模型且有依赖分支**的任务；或**离线/近线批处理**路径。
- 单模型/低延迟场景**保留**现有实现（或 CGraph-lite 单头文件版以降风险）。
- 用 `GDaemon` 承接定时任务、`GMessage` 承接跨相机聚合（与 SP6-a 合流）。

**不建议做**：用 CGraph 整体替换 `Pipeline`（尤其是解码/编码/背压/绘制这些与 SDK 强耦合、且已踩过坑的部分）。

## 7. 触发条件（什么时候值得动）

满足**任意两条**再启动阶段 1：

1. 单任务模型数 ≥ 3 且存在"分支再合并"的依赖（如 crop 后的多路二次推理）。
2. 实测瓶颈是"多模型串行"，而非解码/编码/绘制。
3. 出现"同一套代码适配多种模型组合"的维护痛点（`InferGroup` 特例分支增多）。
4. 需要 CGraph 白送的运维能力（超时/暂停/perf/可视化）且有明确使用方。
5. 需要跨相机/跨 pipeline 的消息编排（SP6-a）。

## 8. 结论

- **可以做，但不要整体替换。** CGraph 的适配面是"**多模型子图**"和"**离线批处理**"，不是"**25fps 逐帧热路径**"。
- 现有关键路径（解码→队列→检测线程→绘制→编码→事件）在延迟与背压语义上是**有意设计的单线程流水**，用 CGraph 重写的收益（可配置性、运维特性）小于风险（延迟、线程超订、背压丢失、回归）。
- **下一步**：先做阶段 0 的基准（尤其"每帧 `process()` 调度开销"与"多模型串行耗时占比"）。这两个数字直接决定 CGraph 是否值得引入；在此之前任何重构都是猜测。
