"""
视频监控模块种子数据 — 独立脚本

用法: uv run python app/scripts/seed_video.py [--env=dev]
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
os.environ["ENVIRONMENT"] = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--env" else "dev"

from app.config.setting import get_settings

get_settings.cache_clear()

from sqlalchemy import func, select, update

from app.core.database import async_db_session
from app.core.logger import log

# ─── Camera Groups ───────────────────────────────────────────────
CAMERA_GROUPS = [
    {
        "name": "大门区域", "parent_id": None,
        "sort_order": 1, "status": True, "description": "园区各出入口"
    },
    {
        "name": "正门", "parent_id": "__PARENT:大门区域",
        "sort_order": 1, "status": True, "description": "主出入口"
    },
    {
        "name": "侧门", "parent_id": "__PARENT:大门区域",
        "sort_order": 2, "status": True, "description": "侧门出入口"
    },
    {
        "name": "办公楼", "parent_id": None,
        "sort_order": 2, "status": True, "description": "办公大楼"
    },
    {
        "name": "一楼大厅", "parent_id": "__PARENT:办公楼",
        "sort_order": 1, "status": True, "description": "大厅入口及前台区域"
    },
    {
        "name": "二楼走廊", "parent_id": "__PARENT:办公楼",
        "sort_order": 2, "status": True, "description": "二楼走廊区域"
    },
    {
        "name": "三楼办公区", "parent_id": "__PARENT:办公楼",
        "sort_order": 3, "status": True, "description": "三楼开放办公区"
    },
    {
        "name": "停车场", "parent_id": None,
        "sort_order": 3, "status": True, "description": "地下及地面停车场"
    },
    {
        "name": "仓库区域", "parent_id": None,
        "sort_order": 4, "status": True, "description": "物资仓库及周边"
    },
    {
        "name": "默认分组", "parent_id": None,
        "sort_order": 99, "status": True, "description": "未分类设备默认分组"
    },
]


# ─── Cameras ─────────────────────────────────────────────────────
def make_cameras(group_ids):
    g = group_ids
    return [
        {
            "name": "正门_全景", "device_type": "IP_CAMERA",
            "rtsp_url_main": "rtsp://admin:admin123@192.168.1.10:554/stream1",
            "rtsp_url_sub": "rtsp://admin:admin123@192.168.1.10:554/stream2",
            "username": "admin", "password": "admin123",
            "status": "ONLINE", "stream_status": "IDLE",
            "group_id": g["正门"], "location": "正门入口上方",
            "brand": "海康威视", "model_name": "DS-2CD3T86FV2-IS",
            "firmware": "V5.7.10", "sort_order": 1,
            "latitude": 30.5728, "longitude": 104.0668,
            "description": "正门全景监控，覆盖进出人员及车辆",
        },
        {
            "name": "正门_车牌识别", "device_type": "IP_CAMERA",
            "rtsp_url_main": "rtsp://admin:admin123@192.168.1.11:554/stream1",
            "username": "admin", "password": "admin123",
            "status": "ONLINE", "stream_status": "IDLE",
            "group_id": g["正门"], "location": "正门车道上方",
            "brand": "海康威视", "model_name": "DS-2CD7A87FWD-LZS",
            "firmware": "V5.6.8", "sort_order": 2,
            "latitude": 30.5729, "longitude": 104.0669,
            "description": "车牌识别专用，1.5 米安装高度",
        },
        {
            "name": "侧门_出入口", "device_type": "IP_CAMERA",
            "rtsp_url_main": "rtsp://admin:pass123@192.168.1.12:554/stream1",
            "rtsp_url_sub": "rtsp://admin:pass123@192.168.1.12:554/stream2",
            "username": "admin", "password": "pass123",
            "status": "ONLINE", "stream_status": "IDLE",
            "group_id": g["侧门"], "location": "侧门保安室旁",
            "brand": "大华", "model_name": "DH-IPC-HFW5441T-AS",
            "firmware": "V4.1.2", "sort_order": 1,
            "latitude": 30.5735, "longitude": 104.0675,
            "description": "侧门人员出入监控",
        },
        {
            "name": "大厅_入口全景", "device_type": "IP_CAMERA",
            "rtsp_url_main": "rtsp://admin:admin888@192.168.1.20:554/stream1",
            "username": "admin", "password": "admin888",
            "status": "ONLINE", "stream_status": "PUSHING",
            "group_id": g["一楼大厅"], "location": "大厅前台正上方",
            "brand": "海康威视", "model_name": "DS-2CD2346G2-IS",
            "firmware": "V5.8.2", "sort_order": 1,
            "latitude": 30.5725, "longitude": 104.0665,
            "description": "大堂入口全景监控，联动门禁",
            "stream_id": "zlm_stream_001",
        },
        {
            "name": "大厅_电梯厅", "device_type": "IP_CAMERA",
            "rtsp_url_main": "rtsp://admin:admin888@192.168.1.21:554/stream1",
            "username": "admin", "password": "admin888",
            "status": "ONLINE", "stream_status": "IDLE",
            "group_id": g["一楼大厅"], "location": "电梯厅天花板",
            "brand": "宇视", "model_name": "IPC-B6341-X3",
            "firmware": "V3.2.1", "sort_order": 2,
            "latitude": 30.5724, "longitude": 104.0664,
            "description": "电梯厅入口监控",
        },
        {
            "name": "二楼走廊_东", "device_type": "IP_CAMERA",
            "rtsp_url_main": "rtsp://admin:admin888@192.168.1.30:554/stream1",
            "username": "admin", "password": "admin888",
            "status": "ONLINE", "stream_status": "IDLE",
            "group_id": g["二楼走廊"], "location": "二楼东侧走廊尽头",
            "brand": "海康威视", "model_name": "DS-2CD3T86FV2-IS",
            "firmware": "V5.7.10", "sort_order": 1,
            "latitude": 30.5730, "longitude": 104.0670,
            "description": "二楼东侧走廊监控",
        },
        {
            "name": "二楼走廊_西", "device_type": "IP_CAMERA",
            "rtsp_url_main": "rtsp://admin:admin888@192.168.1.31:554/stream1",
            "username": "admin", "password": "admin888",
            "status": "OFFLINE", "stream_status": "ERROR",
            "group_id": g["二楼走廊"], "location": "二楼西侧走廊尽头",
            "brand": "大华", "model_name": "DH-IPC-HFW5842T-Z",
            "firmware": "V4.0.5", "sort_order": 2,
            "latitude": 30.5731, "longitude": 104.0671,
            "description": "二楼西侧走廊 — 网络异常，需检修",
        },
        {
            "name": "三楼_开放式办公区", "device_type": "IP_CAMERA",
            "rtsp_url_main": "rtsp://admin:admin888@192.168.1.40:554/stream1",
            "username": "admin", "password": "admin888",
            "status": "ONLINE", "stream_status": "IDLE",
            "group_id": g["三楼办公区"], "location": "三楼天花东北角",
            "brand": "海康威视", "model_name": "DS-2CD2346G2-IS",
            "firmware": "V5.8.2", "sort_order": 1,
            "latitude": 30.5732, "longitude": 104.0672,
            "description": "开放办公区全景监控",
        },
        {
            "name": "停车场_南区", "device_type": "IP_CAMERA",
            "rtsp_url_main": "rtsp://admin:admin666@192.168.1.50:554/stream1",
            "username": "admin", "password": "admin666",
            "status": "ONLINE", "stream_status": "PUSHING",
            "group_id": g["停车场"], "location": "地下停车场南区柱子B12",
            "brand": "海康威视", "model_name": "DS-2CD2T47G2-L",
            "firmware": "V5.7.6", "sort_order": 1,
            "latitude": 30.5715, "longitude": 104.0660,
            "description": "停车场南区车位监控，覆盖 12 个车位",
            "stream_id": "zlm_stream_002",
        },
        {
            "name": "停车场_北区", "device_type": "IP_CAMERA",
            "rtsp_url_main": "rtsp://admin:admin666@192.168.1.51:554/stream1",
            "username": "admin", "password": "admin666",
            "status": "ONLINE", "stream_status": "PUSHING",
            "group_id": g["停车场"], "location": "地下停车场北区柱子A05",
            "brand": "大华", "model_name": "DH-IPC-HFW5441T-AS",
            "firmware": "V4.1.2", "sort_order": 2,
            "latitude": 30.5718, "longitude": 104.0662,
            "description": "停车场北区车位监控",
            "stream_id": "zlm_stream_003",
        },
        {
            "name": "仓库_主入口", "device_type": "GB28181",
            "onvif_address": "192.168.1.60",
            "gb28181_device_id": "34020000001320000001",
            "gb28181_channel_id": "34020000001320000001",
            "username": "admin", "password": "admin999",
            "status": "ONLINE", "stream_status": "IDLE",
            "group_id": g["仓库区域"], "location": "仓库大门上方",
            "brand": "海康威视", "model_name": "DS-2CD3T86FV2-IS",
            "firmware": "V5.7.10", "sort_order": 1,
            "latitude": 30.5740, "longitude": 104.0680,
            "description": "仓库主入口 GB28181 接入",
        },
        {
            "name": "仓库_内部东", "device_type": "IP_CAMERA",
            "rtsp_url_main": "rtsp://admin:admin999@192.168.1.61:554/stream1",
            "username": "admin", "password": "admin999",
            "status": "ONLINE", "stream_status": "IDLE",
            "group_id": g["仓库区域"], "location": "仓库东侧货架上方",
            "brand": "宇视", "model_name": "IPC-B6341-X3",
            "firmware": "V3.2.1", "sort_order": 2,
            "latitude": 30.5741, "longitude": 104.0681,
            "description": "仓库东侧物资监控",
        },
    ]


# ─── Record Plans ────────────────────────────────────────────────
def make_record_plans(camera_ids):
    c = camera_ids
    plans = []
    for idx, cam_id in enumerate(c.values()):
        plan_type = "CONTINUOUS" if idx % 3 != 0 else "SCHEDULE"
        plans.append({
            "camera_id": cam_id,
            "plan_type": plan_type,
            "schedule_json": (
                {
                    "monday": ["00:00-08:00", "18:00-24:00"],
                    "tuesday": ["00:00-08:00", "18:00-24:00"],
                    "wednesday": ["00:00-08:00", "18:00-24:00"],
                    "thursday": ["00:00-08:00", "18:00-24:00"],
                    "friday": ["00:00-08:00", "18:00-24:00"],
                    "saturday": ["00:00-24:00"],
                    "sunday": ["00:00-24:00"],
                }
                if plan_type == "SCHEDULE" else None
            ),
            "pre_record_sec": 5,
            "post_record_sec": 10,
            "storage_days": 30,
            "stream_type": "MAIN",
            "status": True,
            "description": f"{plan_type} 录制计划",
        })
    return plans


# ─── Record Files ────────────────────────────────────────────────
def make_record_files(camera_ids):
    c = camera_ids
    now = datetime.now()
    files = []
    for i, (name, cam_id) in enumerate(c.items()):
        start = now - timedelta(hours=2 + i * 3)
        end = start + timedelta(minutes=15)
        files.append({
            "camera_id": cam_id,
            "stream_id": f"record_{i:03d}",
            "file_path": f"/recordings/{now.strftime('%Y%m%d')}/{cam_id}/{start.strftime('%H%M%S')}.mp4",
            "file_size": 150 + i * 30,
            "duration": 900,
            "start_time": start,
            "end_time": end,
            "record_type": "CONTINUOUS",
            "format": "mp4",
            "status": "COMPLETED",
        })
    return files


# ─── Algorithms ──────────────────────────────────────────────────
ALGORITHMS = [
    {"name": "区域入侵检测", "code": "intrusion_detect", "version": "2.1.0",
     "algorithm_type": "INTRUSION", "status": True,
     "model_path": "/models/intrusion/v2.1.0/engine.onnx",
     "model_file_config": {"format": "onnx", "encrypt": {"enabled": False, "method": None}},
     "runtime_config": {"engine": "tensorrt", "gpu": {"enabled": True, "device_id": 0}, "threads": 4, "batch_size": 1, "input_width": 640, "input_height": 640},
     "preset_params": {"confidence": 0.5, "nms_threshold": 0.45},
     "param_meta": {
         "confidence": {"label": "置信度阈值", "type": "float", "default": 0.5, "min": 0.1, "max": 1.0, "step": 0.05, "unit": "", "hint": "检测置信度阈值，低于此值的结果将被过滤"},
         "nms_threshold": {"label": "NMS 阈值", "type": "float", "default": 0.45, "min": 0.1, "max": 1.0, "step": 0.05, "unit": "", "hint": "非极大值抑制阈值，值越小重复框越少"},
     },
     "description": "基于 YOLOv8 的区域入侵检测"},
    {"name": "越界检测", "code": "line_crossing", "version": "1.8.0",
     "algorithm_type": "LINE_CROSSING", "status": True,
     "model_path": "/models/line_crossing/v1.8.0/engine.onnx",
     "model_file_config": {"format": "onnx", "encrypt": {"enabled": False, "method": None}},
     "runtime_config": {"engine": "tensorrt", "gpu": {"enabled": True, "device_id": 0}, "threads": 4, "batch_size": 1, "input_width": 640, "input_height": 640},
     "preset_params": {"confidence": 0.4, "nms_threshold": 0.4, "line": [[0.3, 0.5], [0.7, 0.5]], "direction": "both"},
     "param_meta": {
         "confidence": {"label": "置信度阈值", "type": "float", "default": 0.4, "min": 0.1, "max": 1.0, "step": 0.05, "unit": "", "hint": "目标检测置信度"},
         "nms_threshold": {"label": "NMS 阈值", "type": "float", "default": 0.4, "min": 0.1, "max": 1.0, "step": 0.05, "unit": "", "hint": "非极大值抑制阈值"},
         "line": {"label": "越界线坐标", "type": "polyline", "default": [[0.3, 0.5], [0.7, 0.5]], "unit": "归一化坐标", "hint": "在画面中绘制一条虚拟线，两点确定一条直线"},
         "direction": {"label": "检测方向", "type": "select", "default": "both", "options": [{"label": "双向", "value": "both"}, {"label": "A→B", "value": "a_to_b"}, {"label": "B→A", "value": "b_to_a"}], "hint": "越界方向过滤器"},
     },
     "description": "电子围栏越界检测"},
    {"name": "人脸检测", "code": "face_detect", "version": "3.2.0",
     "algorithm_type": "FACE_DETECT", "status": True,
     "model_path": "/models/face/v3.2.0/engine.onnx",
     "model_file_config": {"format": "onnx", "encrypt": {"enabled": False, "method": None}},
     "runtime_config": {"engine": "tensorrt", "gpu": {"enabled": True, "device_id": 0}, "threads": 4, "batch_size": 4, "input_width": 640, "input_height": 640},
     "preset_params": {"confidence": 0.6, "nms_threshold": 0.4, "min_face_size": 50, "max_face_size": 500, "similarity_threshold": 0.7},
     "param_meta": {
         "confidence": {"label": "置信度阈值", "type": "float", "default": 0.6, "min": 0.1, "max": 1.0, "step": 0.05, "unit": "", "hint": "人脸检测置信度"},
         "nms_threshold": {"label": "NMS 阈值", "type": "float", "default": 0.4, "min": 0.1, "max": 1.0, "step": 0.05, "unit": "", "hint": "非极大值抑制阈值"},
         "min_face_size": {"label": "最小人脸", "type": "int", "default": 50, "min": 20, "max": 300, "step": 10, "unit": "像素", "hint": "小于此尺寸的人脸将被忽略"},
         "max_face_size": {"label": "最大人脸", "type": "int", "default": 500, "min": 100, "max": 2000, "step": 50, "unit": "像素", "hint": "大于此尺寸的人脸将被忽略"},
         "similarity_threshold": {"label": "比对阈值", "type": "float", "default": 0.7, "min": 0.5, "max": 1.0, "step": 0.05, "unit": "", "hint": "人脸比对相似度阈值，越高越严格"},
     },
     "description": "基于 ArcFace 的人脸检测与比对"},
    {"name": "车辆检测", "code": "vehicle_detect", "version": "1.5.0",
     "algorithm_type": "VEHICLE_DETECT", "status": True,
     "model_path": "/models/vehicle/v1.5.0/engine.onnx",
     "model_file_config": {"format": "onnx", "encrypt": {"enabled": False, "method": None}},
     "runtime_config": {"engine": "tensorrt", "gpu": {"enabled": True, "device_id": 0}, "threads": 4, "batch_size": 1, "input_width": 640, "input_height": 640},
     "preset_params": {"confidence": 0.5, "nms_threshold": 0.45, "vehicle_types": ["car", "truck", "bus", "motorcycle"]},
     "param_meta": {
         "confidence": {"label": "置信度阈值", "type": "float", "default": 0.5, "min": 0.1, "max": 1.0, "step": 0.05, "unit": "", "hint": "车辆检测置信度"},
         "nms_threshold": {"label": "NMS 阈值", "type": "float", "default": 0.45, "min": 0.1, "max": 1.0, "step": 0.05, "unit": "", "hint": "非极大值抑制阈值"},
         "vehicle_types": {"label": "检测车型", "type": "multi-select", "default": ["car", "truck", "bus", "motorcycle"], "options": [{"label": "轿车", "value": "car"}, {"label": "卡车", "value": "truck"}, {"label": "巴士", "value": "bus"}, {"label": "摩托车", "value": "motorcycle"}, {"label": "自行车", "value": "bicycle"}, {"label": "三轮车", "value": "tricycle"}], "hint": "选择需要检测的车辆类型"},
     },
     "description": "车辆类型、颜色、车牌检测"},
    {"name": "烟火检测", "code": "fire_smoke", "version": "2.0.0",
     "algorithm_type": "FIRE_SMOKE", "status": True,
     "model_path": "/models/fire_smoke/v2.0.0/engine.onnx",
     "model_file_config": {"format": "onnx", "encrypt": {"enabled": False, "method": None}},
     "runtime_config": {"engine": "tensorrt", "gpu": {"enabled": True, "device_id": 0}, "threads": 4, "batch_size": 1, "input_width": 640, "input_height": 640},
     "preset_params": {"confidence": 0.5, "nms_threshold": 0.45},
     "param_meta": {
         "confidence": {"label": "置信度阈值", "type": "float", "default": 0.5, "min": 0.1, "max": 1.0, "step": 0.05, "unit": "", "hint": "烟火检测置信度，建议设 0.4~0.6 之间"},
         "nms_threshold": {"label": "NMS 阈值", "type": "float", "default": 0.45, "min": 0.1, "max": 1.0, "step": 0.05, "unit": "", "hint": "非极大值抑制阈值"},
     },
     "description": "基于 YOLOv8 的烟火检测"},
    {"name": "人员聚集检测", "code": "crowd_detect", "version": "1.3.0",
     "algorithm_type": "CROWD_DETECT", "status": False,
     "model_path": "/models/crowd/v1.3.0/engine.onnx",
     "model_file_config": {"format": "onnx", "encrypt": {"enabled": False, "method": None}},
     "runtime_config": {"engine": "tensorrt", "gpu": {"enabled": True, "device_id": 0}, "threads": 4, "batch_size": 1, "input_width": 640, "input_height": 640},
     "preset_params": {"confidence": 0.3, "max_count": 100, "alert_threshold": 50},
     "param_meta": {
         "confidence": {"label": "检测置信度", "type": "float", "default": 0.3, "min": 0.1, "max": 1.0, "step": 0.05, "unit": "", "hint": "人员检测置信度阈值"},
         "max_count": {"label": "人数上限", "type": "int", "default": 100, "min": 10, "max": 500, "step": 10, "unit": "人", "hint": "区域内最多检测人数，超过则停止检测"},
         "alert_threshold": {"label": "告警阈值", "type": "int", "default": 50, "min": 10, "max": 500, "step": 5, "unit": "人", "hint": "超过此人数触发聚集告警"},
     },
     "description": "人员密度/聚集检测（当前版本性能待优化）"},
]


# ─── Algorithm Tasks ─────────────────────────────────────────────
def make_algorithm_tasks(camera_ids, algorithm_ids):
    c, a = camera_ids, algorithm_ids
    return [
        {"camera_id": c["正门_全景"], "algorithm_id": a["区域入侵检测"],
         "stream_type": "SUB", "sensitivity": 70, "status": "RUNNING"},
        {"camera_id": c["大厅_入口全景"], "algorithm_id": a["人脸检测"],
         "stream_type": "SUB", "sensitivity": 60, "status": "RUNNING"},
        {"camera_id": c["停车场_南区"], "algorithm_id": a["车辆检测"],
         "stream_type": "MAIN", "sensitivity": 50, "status": "RUNNING"},
        {"camera_id": c["仓库_主入口"], "algorithm_id": a["区域入侵检测"],
         "stream_type": "SUB", "sensitivity": 80, "status": "RUNNING"},
        {"camera_id": c["仓库_内部东"], "algorithm_id": a["烟火检测"],
         "stream_type": "SUB", "sensitivity": 85, "status": "RUNNING"},
        {"camera_id": c["三楼_开放式办公区"], "algorithm_id": a["人员聚集检测"],
         "stream_type": "SUB", "sensitivity": 50, "status": "STOPPED"},
    ]


# ─── Alarm Rules ─────────────────────────────────────────────────
def make_alarm_rules(camera_ids, algorithm_ids):
    c, a = camera_ids, algorithm_ids
    return [
        {"name": "正门区域入侵告警", "camera_id": c["正门_全景"],
         "alarm_type": "INTRUSION", "algorithm_task_id": None,
         "severity": "CRITICAL", "sensitivity": 80,
         "interval_seconds": 10, "notify_channels": ["WS_PUSH", "SMS"],
         "detect_region": {"points": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.4], [0.1, 0.4]]},
         "status": True, "description": "正门区域入侵 — 夜间自动启用"},
        {"name": "大厅陌生人告警", "camera_id": c["大厅_入口全景"],
         "alarm_type": "FACE_DETECT", "algorithm_task_id": None,
         "severity": "WARNING", "sensitivity": 60,
         "interval_seconds": 30, "notify_channels": ["WS_PUSH"],
         "status": True, "description": "大厅人脸检测 — 陌生人告警"},
        {"name": "停车场车辆违停检测", "camera_id": c["停车场_南区"],
         "alarm_type": "VEHICLE_DETECT", "algorithm_task_id": None,
         "severity": "WARNING", "sensitivity": 50,
         "interval_seconds": 60, "notify_channels": ["WS_PUSH"],
         "detect_region": {"points": [[0, 0], [1, 0], [1, 0.3], [0, 0.3]]},
         "status": True, "description": "停车场出入口违停检测"},
        {"name": "仓库火警预警", "camera_id": c["仓库_内部东"],
         "alarm_type": "FIRE_SMOKE", "algorithm_task_id": None,
         "severity": "CRITICAL", "sensitivity": 90,
         "interval_seconds": 5, "notify_channels": ["WS_PUSH", "SMS", "EMAIL"],
         "status": True, "description": "仓库烟火检测 — 最高级别预警"},
        {"name": "二楼走廊夜间入侵", "camera_id": c["二楼走廊_东"],
         "alarm_type": "INTRUSION", "algorithm_task_id": None,
         "severity": "CRITICAL", "sensitivity": 75,
         "interval_seconds": 15, "notify_channels": ["WS_PUSH"],
         "status": False, "description": "二楼走廊入侵告警（设备离线暂未启用）"},
    ]


# ─── Alarm Records ───────────────────────────────────────────────
def make_alarm_records(camera_ids, rule_ids):
    c, r = camera_ids, rule_ids
    now = datetime.now()
    types_severity = [("INTRUSION", "CRITICAL"), ("FACE_DETECT", "WARNING"),
                      ("VEHICLE_DETECT", "WARNING"), ("MOTION", "INFO"), ("INTRUSION", "CRITICAL"),
                      ("FIRE_SMOKE", "CRITICAL"), ("MOVEMENT", "INFO"), ("FACE_DETECT", "WARNING")]
    statuses = ["PENDING", "CONFIRMED", "IGNORED", "FALSE_ALARM", "PENDING",
                "CONFIRMED", "PENDING", "CONFIRMED"]
    confirm_users = [None, "admin", None, "admin", None, "admin", None, "admin"]
    confirm_times = [None, now - timedelta(minutes=30), None, now - timedelta(hours=2),
                     None, now - timedelta(hours=1), None, now - timedelta(minutes=45)]
    descriptions = [
        "夜间检测到不明人员进入正门区域",
        "陌生人进入大厅 — 人脸比对无匹配记录",
        "停车场出口车辆停留超过 3 分钟",
        "大厅玻璃门附近有轻微移动",
        "仓库东侧红外触发入侵告警",
        "仓库东侧检测到烟雾",
        "电梯厅检测到长时间停留人员",
        "办公楼正门重复出现未授权人员",
    ]
    snapshots = [
        "/snapshots/20260323/intrusion_001.jpg",
        "/snapshots/20260323/face_stranger_002.jpg",
        "/snapshots/20260323/parking_warning_003.jpg",
        "/snapshots/20260323/motion_004.jpg",
        "/snapshots/20260323/intrusion_005.jpg",
        "/snapshots/20260323/fire_detect_006.jpg",
        "/snapshots/20260323/movement_lobby_007.jpg",
        "/snapshots/20260323/face_repeat_008.jpg",
    ]
    cam_names = list(c.keys())
    c_ids = list(c.values())
    r_ids = list(r.values()) + [None] * (len(types_severity) - len(r))
    records = []
    for i, ((alarm_type, severity), status) in enumerate(zip(types_severity, statuses)):
        alarm_time = now - timedelta(hours=i, minutes=i * 13)
        records.append({
            "camera_id": c_ids[i % len(c_ids)],
            "rule_id": r_ids[i],
            "alarm_type": alarm_type,
            "severity": severity,
            "alarm_time": alarm_time,
            "confirm_time": confirm_times[i],
            "confirm_user": confirm_users[i],
            "status": status,
            "snapshot_path": snapshots[i],
            "description": descriptions[i],
            "ai_result": {
                "confidence": round(0.75 + (i * 0.03) % 0.2, 2),
                "model_version": "v2.1.0",
                "raw": {"label": alarm_type, "score": 0.8 + (i * 0.02) % 0.15},
            },
        })
    return records


# ─── Layouts ─────────────────────────────────────────────────────
LAYOUTS = [
    {"name": "四画面布局", "grid_type": "4",
     "layout_config": {
         "grid_type": "4",
         "windows": {},
     }, "is_default": True, "description": "默认四画面 — 覆盖主要出入口"},
    {"name": "九画面布局", "grid_type": "9",
     "layout_config": {
         "grid_type": "9",
         "windows": {},
     }, "is_default": False, "description": "九画面 — 全量设备轮巡"},
    {"name": "重点区域布局", "grid_type": "6",
     "layout_config": {
         "grid_type": "6",
         "windows": {},
     }, "is_default": False, "description": "六画面 — 重点区域直连"},
]


# ─── Event Linkages ──────────────────────────────────────────────
EVENT_LINKAGES = [
    {"name": "入侵联动录像", "trigger_event": "ALARM",
     "trigger_camera_ids": None,
     "action_type": "RECORD", "status": True,
     "action_params": {"pre_sec": 10, "post_sec": 30, "stream": "MAIN"},
     "description": "告警触发后自动开始录像"},
    {"name": "大厅门禁联动", "trigger_event": "MOTION",
     "trigger_camera_ids": None,
     "action_type": "PTZ", "status": True,
     "action_params": {"camera_id": None, "preset": 1},
     "description": "大厅移动检测触发球机预置位"},
    {"name": "火警短信通知", "trigger_event": "ALARM",
     "trigger_camera_ids": None,
     "action_type": "PUSH", "status": True,
     "action_params": {"channels": ["SMS", "EMAIL"], "template": "fire_alert"},
     "description": "火警检测同时发送短信和邮件通知安保负责人"},
    {"name": "夜间告警弹窗", "trigger_event": "ALARM",
     "trigger_camera_ids": None,
     "action_type": "ALERT", "status": True,
     "action_params": {"popup": True, "sound": True, "time_range": ["22:00", "07:00"]},
     "description": "夜间告警自动弹窗并播放提示音"},
]


# ─── Main ────────────────────────────────────────────────────────
async def seed():
    # Import UserModel first to resolve circular dependency in UserMixin relationships
    from app.api.v1.module_system.user.model import UserModel  # noqa: F401
    from app.api.v1.module_video.alarm.model import AlarmRecordModel, AlarmRuleModel
    from app.api.v1.module_video.algorithm.model import AlgorithmModel, AlgorithmTaskModel
    from app.api.v1.module_video.camera.model import CameraGroupModel, CameraModel
    from app.api.v1.module_video.event.model import EventLinkageModel
    from app.api.v1.module_video.layout.model import LayoutModel
    from app.api.v1.module_video.record.model import RecordFileModel, RecordPlanModel

    async with async_db_session() as db:
        async with db.begin():
            # Check which tables already have data
            tables_to_check = [
                ("摄像机分组", CameraGroupModel),
                ("摄像机", CameraModel),
                ("录制计划", RecordPlanModel),
                ("录制文件", RecordFileModel),
                ("算法", AlgorithmModel),
                ("算法任务", AlgorithmTaskModel),
                ("告警规则", AlarmRuleModel),
                ("告警记录", AlarmRecordModel),
                ("布局方案", LayoutModel),
                ("事件联动", EventLinkageModel),
            ]

            skip = {}
            for label, model in tables_to_check:
                result = await db.execute(select(func.count()).select_from(model))
                skip[label] = result.scalar() > 0

            # 1. Camera Groups (insert roots first, then resolve parent references)
            if not skip["摄像机分组"]:
                roots = [g for g in CAMERA_GROUPS if g["parent_id"] is None]
                children = [g for g in CAMERA_GROUPS if g["parent_id"] is not None]

                parent_map = {}
                for g in roots:
                    obj = CameraGroupModel(**{k: v for k, v in g.items() if k != "id"})
                    db.add(obj)
                    await db.flush()
                    parent_map[g["name"]] = obj.id

                for g in children:
                    parent_name = g["parent_id"][9:]  # strip "__PARENT:"
                    g["parent_id"] = parent_map[parent_name]
                    obj = CameraGroupModel(**{k: v for k, v in g.items() if k != "id"})
                    db.add(obj)
                    await db.flush()

                log.info("✅ 已插入摄像机分组数据")
            else:
                log.info("⏭️ 摄像机分组表已有数据，跳过")

            # Get group ID mapping
            result = await db.execute(select(CameraGroupModel))
            all_groups = {g.name: g.id for g in result.scalars().all()}

            # 2. Cameras
            group_ids = {
                "正门": all_groups.get("正门"),
                "侧门": all_groups.get("侧门"),
                "一楼大厅": all_groups.get("一楼大厅"),
                "二楼走廊": all_groups.get("二楼走廊"),
                "三楼办公区": all_groups.get("三楼办公区"),
                "停车场": all_groups.get("停车场"),
                "仓库区域": all_groups.get("仓库区域"),
            }
            cameras_data = make_cameras(group_ids)
            camera_ids = {}
            if not skip["摄像机"]:
                objs = [CameraModel(**c) for c in cameras_data]
                db.add_all(objs)
                await db.flush()
                for obj, data in zip(objs, cameras_data):
                    camera_ids[data["name"]] = obj.id
                log.info("✅ 已插入摄像机数据")
            else:
                result = await db.execute(select(CameraModel))
                camera_ids = {g.name: g.id for g in result.scalars().all()}

            # 3. Record Plans
            if not skip["录制计划"]:
                plans = make_record_plans(camera_ids)
                objs = [RecordPlanModel(**p) for p in plans]
                db.add_all(objs)
                log.info("✅ 已插入录制计划数据")
            else:
                log.info("⏭️ 录制计划表已有数据，跳过")

            # 4. Record Files
            if not skip["录制文件"]:
                files = make_record_files(camera_ids)
                objs = [RecordFileModel(**f) for f in files]
                db.add_all(objs)
                log.info("✅ 已插入录制文件数据")
            else:
                log.info("⏭️ 录制文件表已有数据，跳过")

            # 5. Algorithms
            algo_ids = {}
            if not skip["算法"]:
                objs = [AlgorithmModel(**a) for a in ALGORITHMS]
                db.add_all(objs)
                await db.flush()
                for obj, data in zip(objs, ALGORITHMS):
                    algo_ids[data["name"]] = obj.id
                log.info("✅ 已插入算法数据")
            else:
                # Update existing algorithm records with latest seed data
                for a in ALGORITHMS:
                    stmt = (
                        update(AlgorithmModel)
                        .where(AlgorithmModel.code == a["code"])
                        .values(
                            model_file_config=a.get("model_file_config", {}),
                            runtime_config=a.get("runtime_config", {}),
                            preset_params=a.get("preset_params", {}),
                            param_meta=a.get("param_meta", {}),
                        )
                    )
                    await db.execute(stmt)
                await db.flush()
                result = await db.execute(select(AlgorithmModel))
                algo_ids = {g.name: g.id for g in result.scalars().all()}
                log.info("✅ 已更新算法数据")

            # 6. Algorithm Tasks
            if not skip["算法任务"]:
                tasks = make_algorithm_tasks(camera_ids, algo_ids)
                objs = [AlgorithmTaskModel(**t) for t in tasks]
                db.add_all(objs)
                log.info("✅ 已插入算法任务数据")
            else:
                log.info("⏭️ 算法任务表已有数据，跳过")

            # 7. Alarm Rules
            rule_ids = {}
            if not skip["告警规则"]:
                rules = make_alarm_rules(camera_ids, algo_ids)
                objs = [AlarmRuleModel(**r) for r in rules]
                db.add_all(objs)
                await db.flush()
                for obj, data in zip(objs, rules):
                    rule_ids[data["name"]] = obj.id
                log.info("✅ 已插入告警规则数据")
            else:
                result = await db.execute(select(AlarmRuleModel))
                rule_ids = {g.name: g.id for g in result.scalars().all()}

            # 8. Alarm Records
            if not skip["告警记录"]:
                records = make_alarm_records(camera_ids, rule_ids)
                objs = [AlarmRecordModel(**r) for r in records]
                db.add_all(objs)
                log.info("✅ 已插入告警记录数据")
            else:
                log.info("⏭️ 告警记录表已有数据，跳过")

            # 9. Layouts
            if not skip["布局方案"]:
                objs = [LayoutModel(**l) for l in LAYOUTS]
                db.add_all(objs)
                log.info("✅ 已插入布局方案数据")
            else:
                log.info("⏭️ 布局方案表已有数据，跳过")

            # 10. Event Linkages
            if not skip["事件联动"]:
                objs = [EventLinkageModel(**e) for e in EVENT_LINKAGES]
                db.add_all(objs)
                log.info("✅ 已插入事件联动数据")
            else:
                log.info("⏭️ 事件联动表已有数据，跳过")

    summary = []
    for label, model in tables_to_check:
        async with async_db_session() as db:
            r = await db.execute(select(func.count()).select_from(model))
            summary.append(f"{label}: {r.scalar()}")
    print("\n📊 数据汇总:")
    for s in summary:
        print(f"  {s}")


if __name__ == "__main__":
    asyncio.run(seed())
