# service.py 拆分基线快照（2026-11-08）

拆分前先固定一组可对照的数字。后续每个任务的验收都用**同一组命令**，只允许"变好"或"不变"。

## 代码规模

| 文件 | 行数 |
|---|---|
| `backend/app/plugin/module_ai/query/service.py` | 11,041 |
| 其中 `class AiQueryService` | 9,010（249 个方法） |
| 模块级函数/常量（行 1~2030） | ~2,000 |

## 测试基线

命令：

```bash
cd backend
.\.venv\Scripts\python.exe -m pytest tests -k "query or ont or policy" -q
```

结果：**1309 passed, 5 failed, 1 skipped, 2596 deselected（63.7s）**

### 已知失败（拆分前即存在，非本次引入）

用提交 `a152626a`（今天改动之前）新建 worktree 复跑，**同样 7 条失败**，逐条一致：

| 用例 | 现象 |
|---|---|
| `test_cron_run_api.py::test_run_target_agent_consumes_stream` | 键缺失 |
| `test_cron_run_api.py::test_run_target_collects_run_content_text` | 断言失败 |
| `test_cron_run_api.py::test_run_target_collects_tool_calls` | 断言失败 |
| `test_ontology.py::TestTableLevelAcl::test_dq_warning` | `assert False` |
| `test_query_object_e2e.py::test_object_path_returns_object_answer` | 对象路径返回 None（问句含"分布"，被分组/聚合守卫直接降级） |
| `test_query_object_e2e.py::test_ask_stream_yields_ir_event` | 同上 |
| `test_query_object_metric_path.py::test_object_query_path_attempts_custom_ds` | 同上 |

> 说明：`-k` 子集与单文件跑的条数不同（子集 5 条 / 单文件 7 条），因为子集筛选掉了部分 cron 用例。
> 判定标准是"失败集合不新增"，不是"失败数为 0"。

## 冒烟基线

| 命令 | 期望输出 |
|---|---|
| `scripts/query_golden_smoke.py` | 末行 `全部通过` |
| `scripts/query_policy_smoke.py` | `权限网关冒烟通过 8/8` |
| `frontend/scripts/golden_path.mjs` | `全部通过` |

## 已完成

- Task 2（`degraded.py` 抽取）已落地：`service.py` 保留 `_degrade` / `degraded_status` /
  `reset_degraded` 同名再导出，调用点零改动；`test_query_degraded.py` 3 项通过。
