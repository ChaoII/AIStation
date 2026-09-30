# TorchKiln 训练执行改为「每任务一容器」

> 状态：**P0 已实现并端到端验证通过**（2026-09-30）。
> 本文记录最终架构、职责边界、实测数据与踩过的坑。

## 一、一句话结论

TorchKiln 服务**不再以「一个常驻服务接所有训练」的方式运行**。每个训练任务起一个
独立容器，容器内跑完整的 TorchKiln 服务（监听 8000），映射到宿主机的不同端口；
本项目为每个任务各连各的端口、各监控各的容器。
**隔离由容器提供，HTTP 契约一行不改。**

## 二、三个角色与职责边界

| 角色 | 负责 | 明确**不**做 |
|---|---|---|
| **AIStation 后端** | ① 导出标注数据<br>② 作业排队 + 端口/GPU 分配<br>③ `run_container` 起/监控 job 容器<br>④ 消费该端口的日志与指标 | 不解析模型结构 |
| **job 容器**（`torchkiln:0.1.0`，一次一任务） | ① 挂载自己的数据目录<br>② 数据校验 → 训练 → 产出 `metrics.jsonl` 与权重 | 不排队；看不到其他任务的数据；任务结束即销毁 |
| **TorchKiln 常驻服务** | 只提供模型清单（124 个）与超参 schema | **不执行训练**（详见第六节） |

与项目里 ultralytics / PaddleX 的既有做法一致（`scheduler.py:522`、
`paddlex_executor.py:192` 等 5 处都是 `run_container` 一任务一容器），
本次只是把 TorchKiln 拉回同一条路，不引入新范式。

## 三、数据流

```
用户提交训练任务
  ├─ ① 导出标注数据到宿主目录
  │     {SHARED}/train_output/{task_id}/data/
  │       images/{train,val}/*.jpg   labels/{train,val}/*.txt
  │       train.txt  val.txt  dataset.yaml
  │
  ├─ ② 分配端口 + GPU（gpu_pool：Redis 原子分配 + NVML 空闲判定）
  │
  ├─ ③ docker run -p {port}:8000 -v {export_dir}:/workspace \
  │      -e TKILN_DATA_ROOT=/workspace --gpus '"device=0"'
  │      容器内跑完整 TorchKiln 服务
  │
  ├─ ④ 轮询 http://127.0.0.1:{port}/healthz 直到就绪
  │
  └─ ⑤ 提交 job，消费该端口的 SSE 日志/指标 → 落库
        训练结束 → 停容器 → 归还 GPU 与端口 → 产物进 7 天清理
```

**关键约定**：JobSpec 里的路径是**容器内路径** `/workspace/data`。
文件实际写在宿主上，但 TorchKiln 在容器里读；传宿主路径（`C:\...`）必然
`FileNotFoundError`，且必须用 `posixpath` 拼接（反斜杠在容器里不是合法路径）。

## 四、GPU / 端口资源池

`app/plugin/module_train/gpu_pool.py`。空闲判定**双条件，缺一不可**：

| 层 | 判据 | 缺了会怎样 |
|---|---|---|
| 调度层 | Redis 记录该卡/该端口无活跃作业 | 平台自己超发，两任务抢同一张卡 |
| 资源层 | NVML **可用显存 ≥ 本次训练需要的量** | 漏掉**平台外**占用（用户手动起的调试容器） |

资源层用**绝对可用显存**而不是「已用占比 < x%」，这是实测逼出来的（见第九节）。

- 端口**必须真实 bind 探测**（Redis 说空闲不代表没被本机其它进程占）。
  探测故意不设 `SO_REUSEADDR`——Windows 上它允许抢占已绑定端口，会假阳性。
- 拿不到足够 GPU 时，**已认领的端口和那几张卡都要归还**，否则等待一轮后它们
  仍挂在那个 `task_id` 名下，下一轮永远抢不到（泄漏）。
- 一张卡都枚举不到时**降级为「不指定 --gpus」**，不能死等——否则无 GPU 的机器
  上训练任务会永远卡在排队。
- 占用键带 24h TTL 兜底（进程被 `kill -9` 时释放逻辑不会执行）。
- Redis 不可用时降级到进程内字典：端口仍安全（真实 bind 探测），GPU 可能被
  多 worker 超发——宁可放行也不要因为 Redis 挂了就完全不能训练。
- 认领到 Redis 之后会**复查一次显存**，防止判定的间隙里被外部进程抢走。

## 五、目录隔离

容器**只挂载自己那一个任务目录**，于是容器内进程天然看不到其他任务的数据——
隔离由容器保证，不靠代码里的权限判断。per-user 目录层
（`{SHARED}/users/{user_id}/...`，用 AIStation 登录用户的 `id` 而非 OS 用户）
列入 P1：它防的是「有人猜到别的 task_id 路径去挂载」，属于加固而非必需。

## 六、常驻服务的处置

按评审结论：**保留 TorchKiln 常驻服务，但只提供元数据**（模型清单 124 个 +
超参 schema，供前端动态表单），**不再执行训练**。

代价与收益：
- 收益：它不加载 torch、不跑训练 → 「环境不可控」和「故障域过大」的根源被消除。
- 代价：多一个常驻进程、一个端口、一套 token。
- 备选（未采纳）：元数据静态化为 `models.json`，常驻服务彻底退役。
  已实测平台 venv 可以 `import ptcore.config_schema`（**0.66 秒、不碰 torch、
  124 个模型全拿到**），技术上可行；但会引入「模型清单何时刷新、谁负责刷新」
  的新管理负担，故暂不做。

## 七、改动清单与实现现状

| 位置 | 改动 | 状态 |
|---|---|---|
| `gpu_pool.py`（新） | 端口池 + GPU 池 + 就绪探测 | ✅ |
| `torchkiln_executor.py` | 起容器/等就绪/per-task 客户端/资源回收；`reattach` 覆盖 | ✅ |
| `_attach_dataset_lists` | 宿主探测 + 容器内 posix 路径 | ✅ |
| `exporter._fetch_torchkiln_weights` | 改为读宿主挂载目录，不再连服务下载 | ✅ |
| `docker_utils` | 新增 `get_container_labels`（恢复时读回端口） | ✅ |
| `_concurrency` | 8 → 16（原值理由是「排队交给常驻服务」，已不成立） | ✅ |
| `setting.py` | 新增 8 个 job 容器配置项 | ✅ |
| `tests/test_torchkiln_job_container.py`（新） | 10 个守卫测试 | ✅ |
| eval / predict / deploy 三处 | 同构改造 | ⏳ P1 |
| per-user 目录层 + cleanup 适配 | | ⏳ P1 |
| 前端「排队中/等待 GPU/运行于 GPU 0」 | | ⏳ P1 |

## 八、实测结果

端到端跑通一次真实训练（`yolo11-seg`，dataset 9 / 19 图，1 epoch）：

| 指标 | 结果 |
|---|---|
| 最终状态 | `SUCCESS`，`error_log` 为空 |
| **总耗时** | **33.3 秒**（其中训练 14.1 秒） |
| 容器就绪 | **1.8 秒** |
| 指标 | 8 行，首行 `loss_box=0.823 / loss_mask=2.180`（真实梯度，非空数据集） |
| 产物（宿主目录） | `best_accuracy.pth` 11.6MB、`final.pth`、`latest.pth`、`metrics.jsonl`、`train.log` |
| 权重入库 | 成功，`model_repo_id=116` |
| 资源回收 | 池状态 `_local={}` `_local_ports={}`，无泄漏 |

**一个被推翻的预估**：改造前我判断「容器内 `import torch` 要 23.4 秒，每任务固定
开销 25~30 秒」。实测就绪只要 **1.8 秒**——因为上一轮做 runtime 探测时用子进程
隔离了 `import torch`（`registry._probe_runtime_in_subprocess`），服务启动路径
根本不加载 torch。这个改造同时把启动开销也优化掉了。

## 九、踩过的坑（都已修，注释留在代码里）

1. **Docker SDK 的 `ports` 语义是「key=容器内端口，value=宿主机端口」**。
   按直觉写成宿主在前，Docker 会去绑**宿主机**的 8000，直接撞上已在运行的常驻服务。
2. **`volumes` 的值必须是 `{"bind": ..., "mode": ...}`**，不能写裸字符串，
   否则 SDK 对 str 调 `.get()` 抛 `AttributeError`。
3. **拿不到 GPU 时必须归还已认领的端口和部分卡**，否则等待一轮后永久泄漏。
4. **`TKILN_DATA_ROOT` 必须指向挂载点**，否则 `metrics.jsonl` 和权重留在容器可写层，
   容器一销毁全没——而任务还会显示成功，事后才发现没产物。
5. **容器 running ≠ 服务可用**：必须轮询 `/healthz`（虽然本机实测只要 1.8 秒，
   但慢机器上 `import torch` 仍要 20~30 秒，超时上限留 180 秒）。
6. **GPU 空闲判据不能用「已用占比 < 5%」**。实测本机是带桌面环境的 Windows：
   `dwm.exe` + Edge 硬件加速就**常驻占 3.2GB / 20%**，而一个正在训练的任务才占 28%。
   按占比判会得出「卡被占满、不敢派活」，于是**平台在这台机器上永远排队**——
   而这不是理论风险，是第一次跑池就撞上的。改为「可用显存 ≥ 本次训练需要的量」，
   阈值由任务自己的 `resources.gpu_memory_gb` 给出。改完实测：需要 4GB 正常派发，
   需要 15GB 时明确拒绝并打印「GPU0 可用 12.8GB（本次需要 15.0GB）」。

   同一次排查还发现两个**孤儿训练进程**（父进程已死）占着 1.3GB 显存——它们恰好
   实证了双条件判定的价值：Redis 调度层不认识它们（旧的常驻服务模式起的），
   但 NVML 资源层发现了占用并正确拒绝派卡。若只有调度层，训练会直接 OOM。

## 十、下一步（P1）

- eval / predict / deploy 三处同构改造
- per-user 目录层（`users/{user_id}`）+ `cleanup` 适配
- 前端展示排队状态
- 多用户配额（同一用户最多占 N 张卡，防饿死他人）
- 端口/GPU 占用的看门狗（异常退出容器的兜底回收）
