"""为对象查询 A/B 建立微型「系统库」本体对象域（可重复执行，幂等 upsert）。

只在**真实系统表**上建对象（backing_table = 系统表、datasource_id=None），
这样对象查询会视为「已物化」且走系统库。用于评测集里构造对象/多跳类问题。

用法（backend 下）::

    python scripts/_seed_ab_object_domain.py
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", os.environ.get("ENVIRONMENT", "dev"))
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

DOMAIN = "ab_objects"

# 每个对象：code -> dict(table, key_prop, name_prop, props[{code,name,src}])
OBJECTS: dict[str, dict] = {
    "annotation_dataset": {
        "name": "标注数据集", "plural_name": "标注数据集", "api_name": "annotation-datasets",
        "backing_table": "annotation_dataset", "key_prop": "id", "name_prop": "name",
        "props": [
            {"code": "name", "name": "名称", "source_col": "name"},
            {"code": "image_count", "name": "图片数", "source_col": "image_count"},
            {"code": "annotated_count", "name": "已标注数", "source_col": "annotated_count"},
        ],
    },
    "annotation_task": {
        "name": "标注任务", "plural_name": "标注任务", "api_name": "annotation-tasks",
        "backing_table": "annotation_task", "key_prop": "id", "name_prop": "name",
        "props": [
            {"code": "name", "name": "名称", "source_col": "name"},
            {"code": "dataset_id", "name": "数据集ID", "source_col": "dataset_id"},
            {"code": "status", "name": "状态", "source_col": "status"},
            {"code": "task_type", "name": "任务类型", "source_col": "task_type"},
        ],
    },
    "ai_apps": {
        "name": "AI应用", "plural_name": "AI应用", "api_name": "ai-apps",
        "backing_table": "ai_apps", "key_prop": "id", "name_prop": "name",
        "props": [
            {"code": "name", "name": "名称", "source_col": "name"},
            {"code": "enabled", "name": "启用", "source_col": "enabled"},
            {"code": "model_id", "name": "模型ID", "source_col": "model_id"},
        ],
    },
    "ai_call_logs": {
        "name": "模型调用日志", "plural_name": "模型调用日志", "api_name": "ai-call-logs",
        "backing_table": "ai_call_logs", "key_prop": "id", "name_prop": "model_name",
        "props": [
            {"code": "model_name", "name": "模型名", "source_col": "model_name"},
            {"code": "app_id", "name": "应用ID", "source_col": "app_id"},
            {"code": "status", "name": "状态", "source_col": "status"},
            {"code": "latency_ms", "name": "延迟ms", "source_col": "latency_ms"},
        ],
    },
    "ai_models": {
        "name": "AI模型", "plural_name": "AI模型", "api_name": "ai-models",
        "backing_table": "ai_models", "key_prop": "id", "name_prop": "name",
        "props": [
            {"code": "name", "name": "名称", "source_col": "name"},
            {"code": "provider", "name": "提供商", "source_col": "provider"},
            {"code": "enabled", "name": "启用", "source_col": "enabled"},
        ],
    },
    # 仅用**干净**的 alarm_type 维度（severity/status 全相同，不作为维度）。
    # camera_id 0 悬空，但 video_cameras 本身数据脏（55 行仅 1 非删），故不建 camera 链接。
    "video_alarm_records": {
        "name": "视频告警记录", "plural_name": "视频告警记录", "api_name": "video-alarm-records",
        "backing_table": "video_alarm_records", "key_prop": "id", "name_prop": "alarm_type",
        "props": [
            {"code": "alarm_type", "name": "告警类型", "source_col": "alarm_type"},
            {"code": "severity", "name": "级别", "source_col": "severity"},
            {"code": "status", "name": "状态", "source_col": "status"},
            {"code": "camera_id", "name": "摄像头ID", "source_col": "camera_id"},
        ],
    },
}

# 链接：source -> target（source_field -> target_field）
LINKS: list[dict] = [
    {"source_object": "annotation_dataset", "target_object": "annotation_task",
     "name": "数据集_标注任务", "source_field": "id", "target_field": "dataset_id",
     "card": "one_to_many", "source_name": "标注数据集", "target_name": "标注任务"},
    {"source_object": "ai_apps", "target_object": "ai_call_logs",
     "name": "应用_调用日志", "source_field": "id", "target_field": "app_id",
     "card": "one_to_many", "source_name": "AI应用", "target_name": "模型调用日志"},
]


async def main() -> None:
    from app.plugin.module_ai.ontology import service as O

    for code, spec in OBJECTS.items():
        d = dict(code=code, domain_code=DOMAIN, **spec)
        r = await O.upsert_object(d)
        print(f"object {code}: {r}")
        for p in spec["props"]:
            rp = await O.upsert_property({
                "object_code": code, "code": p["code"], "name": p["name"],
                "prop_type": "string", "source_col": p.get("source_col", p["code"]),
                "visibility": "normal",
            })
            print(f"   prop {code}.{p['code']}: {rp}")
    for lk in LINKS:
        rl = await O.upsert_link(lk)
        print(f"link {lk['source_object']}->{lk['target_object']}: {rl}")

    # 缓慢验证：对象规格 + 实例层 pivot 能不能跑
    from app.plugin.module_ai.query.service import AiQueryService
    from types import SimpleNamespace
    auth = SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True))
    spec = await AiQueryService._object_spec_for("annotation_dataset")
    print("dataset spec:", "OK" if spec else "FAIL", spec)
    spec2 = await AiQueryService._object_spec_for("annotation_task")
    print("task spec:", "OK" if spec2 else "FAIL")
    spec3 = await AiQueryService._object_spec_for("ai_call_logs")
    print("call_logs spec:", "OK" if spec3 else "FAIL")
    spec4 = await AiQueryService._object_spec_for("ai_apps")
    print("ai_apps spec:", "OK" if spec4 else "FAIL")
    spec5 = await AiQueryService._object_spec_for("ai_models")
    print("ai_models spec:", "OK" if spec5 else "FAIL")


asyncio.run(main())
