"""
Inference Worker — standalone subprocess.

Usage:
    python worker.py --config /path/to/config.json

Stdout: reserved for debug prints (captured by scheduler for logging).
Stderr: JSON lines for machine-parseable events (heartbeat, detection, error, shutdown).

Signal handling:
    SIGTERM / SIGINT → set stop_flag → graceful shutdown after current frame.
"""
from __future__ import annotations

import argparse
import base64
import json
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# worker 作为独立子进程运行，需把 backend 根加入 sys.path 以导入 app 包
_BACKEND_ROOT = Path(__file__).resolve().parents[4]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def load_config(path: str) -> dict:
    with open(path) as f:
        cfg = json.load(f)
    return cfg


def within_schedule(schedule_json, now) -> bool:
    """判断当前时间是否在布控时段内；无配置或解析失败→True（不误停）。

    支持两种格式：
    - 前端实际下发：``{"type": "weekly", "slots": [{"day": 0-6, "start": 0-24, "end": 0-24}]}``
      （day 以周一为 0，start 含、end 不含）
    - 简化/兼容：``{"days": [0-6], "start": "HH:MM", "end": "HH:MM"}``
      或 ``{"ranges": [["HH:MM", "HH:MM"], ...]}``
    """
    if not schedule_json:
        return True
    try:
        cfg = schedule_json if isinstance(schedule_json, dict) else json.loads(schedule_json)
        if not isinstance(cfg, dict):
            return True

        # 前端 weekly slots 格式（day 与 datetime.weekday() 一致，周一=0）
        slots = cfg.get("slots")
        if isinstance(slots, list) and slots:
            day = now.weekday()
            hour = now.hour
            for s in slots:
                if not isinstance(s, dict):
                    continue
                if int(s.get("day")) != day:
                    continue
                if int(s.get("start", 0)) <= hour < int(s.get("end", 24)):
                    return True
            return False

        days = cfg.get("days")
        if days and now.weekday() not in days:
            return False
        start = cfg.get("start")
        end = cfg.get("end")
        if start and end:
            hm = now.strftime("%H:%M")
            if start <= end:
                return start <= hm <= end
            return hm >= start or hm <= end  # 跨天
        ranges = cfg.get("ranges")
        if isinstance(ranges, list):
            hm = now.strftime("%H:%M")
            return any(
                isinstance(r, (list, tuple)) and len(r) == 2 and r[0] <= hm <= r[1]
                for r in ranges
            )
    except Exception:
        return True
    return True


def sensitivity_to_conf(sensitivity, base: float = 0.5) -> float:
    """灵敏度(0-100) → 置信度阈值：越高阈值越低，clamp 到 [0.05, 0.95]。"""
    try:
        s = max(0, min(100, int(sensitivity)))
    except (TypeError, ValueError):
        s = 50
    conf = base * (1 - (s - 50) / 100.0)
    return max(0.05, min(0.95, conf))


def label_name(result, names: list | None = None) -> str:
    """结果标签名：优先 result.label，其次外部名称表，最后数字 id。"""
    lbl = getattr(result, "label", None)
    if lbl:
        return str(lbl)
    lid = getattr(result, "label_id", None)
    if names and lid is not None and 0 <= int(lid) < len(names):
        return str(names[int(lid)])
    return str(lid)


def stderr_json(**kwargs):
    """Emit a JSON line to stderr for machine parsing."""
    kwargs["t"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:23] + "Z"
    sys.stderr.write(json.dumps(kwargs, ensure_ascii=False) + "\n")
    sys.stderr.flush()


def create_model(config: dict):
    """Initialize ModelDeploy model from config."""
    from app.api.v1.module_video.inference.registry import create_model as _create_model

    model = _create_model(
        algorithm_type=config["algorithm_type"],
        model_path=config["model_path"],
        runtime_config=config.get("runtime_config"),
    )

    params = config.get("preset_params", {})
    if hasattr(model, "postprocessor"):
        # 预设未显式给阈值时由灵敏度推导，保证灵敏度配置真正生效
        conf = params.get("conf_threshold", params.get("confidence"))
        if conf is None:
            conf = sensitivity_to_conf(config.get("sensitivity", 50))
        model.postprocessor.conf_threshold = conf
        model.postprocessor.nms_threshold = params.get("nms_threshold", 0.45)

    return model


def draw_detections(frame, detections, color_map):
    """Draw bounding boxes and labels on the frame."""
    import cv2
    h, w = frame.shape[:2]
    for d in detections:
        bbox = d["bbox"]
        x1 = int(bbox["x"] * w)
        y1 = int(bbox["y"] * h)
        x2 = int((bbox["x"] + bbox["width"]) * w)
        y2 = int((bbox["y"] + bbox["height"]) * h)
        label = d["label"]
        conf = d["confidence"]
        color = color_map.get(label, (64, 128, 255))

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        text = f"{label} {conf:.2f}"
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(frame, (x1, y1 - th - 4), (x1 + tw + 4, y1), color, -1)
        cv2.putText(frame, text, (x1 + 2, y1 - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

    return frame


def apply_roi(frame, region):
    """Apply ROI mask. region is a list of [x, y] normalized coordinates, or a dict."""
    import cv2
    import numpy as np
    if not region:
        return frame
    # detect_region 存为 JSONB dict 时可能为 {points: [[x,y]...]} 或 {x1,y1,x2,y2}
    if isinstance(region, dict):
        if isinstance(region.get("points"), list) and region["points"]:
            region = region["points"]
        elif "x1" in region and "x2" in region:
            region = [[region["x1"], region["y1"]], [region["x2"], region["y1"]],
                      [region["x2"], region["y2"]], [region["x1"], region["y2"]]]
        else:
            return frame
    h, w = frame.shape[:2]
    pts = np.array([[[int(x * w), int(y * h)] for x, y in region]], dtype=np.int32)
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillPoly(mask, pts, 255)
    return cv2.bitwise_and(frame, frame, mask=mask)


def main():
    import cv2
    import httpx

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="Path to config JSON")
    args = parser.parse_args()

    config = load_config(args.config)
    task_id = config["task_id"]
    algorithm_type = config["algorithm_type"]
    stream_url = config["stream_url"]
    callback_url = config.get("callback_url")
    callback_token = config.get("callback_token", "")
    fps_target = config.get("fps_target", 5)
    # 告警去重间隔：优先 interval_seconds，兼容旧键 alarm_interval
    alarm_interval = config.get("interval_seconds", config.get("alarm_interval", 30))
    snapshot_dir = config.get("snapshot_dir", "data/detections")
    _pp = config.get("preset_params", {}) or {}
    # seed 用 confidence，部分配置用 conf_threshold——兼容两者；
    # 预设未给时由灵敏度推导，保证灵敏度配置真正生效
    if "conf_threshold" in _pp:
        conf_threshold = _pp["conf_threshold"]
    elif "confidence" in _pp:
        conf_threshold = _pp["confidence"]
    else:
        conf_threshold = sensitivity_to_conf(config.get("sensitivity", 50))
    detect_region = config.get("detect_region")
    schedule_json = config.get("schedule_json")
    class_names = config.get("class_names") or None

    stderr_json(type="init", task=task_id, algorithm=algorithm_type, stream=stream_url)

    # Initialize model
    try:
        model = create_model(config)
        stderr_json(type="model_loaded", task=task_id)
    except Exception as e:
        stderr_json(type="error", task=task_id, msg=f"model_load_failed: {e}")
        sys.exit(1)

    # Open stream
    cap = cv2.VideoCapture(stream_url)
    if not cap.isOpened():
        stderr_json(type="error", task=task_id, msg="stream_open_failed")
        sys.exit(1)

    stop_flag = [False]

    def handle_signal(signum, frame):
        stop_flag[0] = True
        stderr_json(type="signal", task=task_id, signal=signum)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    # State
    frame_count = 0
    total_detections = 0
    start_time = time.time()
    last_alarm_time: dict[str, float] = {}
    color_map = {
        "person": (0, 0, 255),
        "car": (255, 0, 0),
        "bicycle": (0, 255, 0),
        "motorcycle": (255, 165, 0),
        "bus": (128, 0, 128),
        "truck": (0, 128, 128),
        "fire": (0, 0, 255),
        "smoke": (128, 128, 128),
    }

    skip = max(1, int(30 / max(fps_target, 1)))

    while not stop_flag[0]:
        ret, frame = cap.read()
        if not ret:
            stderr_json(type="warn", task=task_id, msg="frame_read_failed")
            time.sleep(1)
            cap.release()
            cap = cv2.VideoCapture(stream_url)
            continue

        frame_count += 1

        if frame_count % skip != 0:
            continue

        # 布控时段外：跳过推理（配置为空/解析失败时不误停）
        if not within_schedule(schedule_json, datetime.now()):
            time.sleep(1)
            continue

        # ROI mask
        if detect_region:
            frame_masked = apply_roi(frame, detect_region)
        else:
            frame_masked = frame

        # Infer
        t0 = time.time()
        try:
            results = model.predict(frame_masked)
        except Exception as e:
            stderr_json(type="error", task=task_id, msg=f"inference_failed: {e}")
            continue
        latency_ms = (time.time() - t0) * 1000

        alarms = []
        for r in results:
            label_id = r.label_id
            score = r.score
            if score < conf_threshold:
                continue
            box = r.box

            label = label_name(r, class_names)
            now = time.time()
            last = last_alarm_time.get(label, 0)
            if now - last < alarm_interval:
                continue
            last_alarm_time[label] = now

            alarms.append({
                "label": label,
                "label_id": label_id,
                "confidence": round(float(score), 4),
                "bbox": {
                    "x": round(float(box.x), 4),
                    "y": round(float(box.y), 4),
                    "width": round(float(box.width), 4),
                    "height": round(float(box.height), 4),
                },
            })

        total_detections += len(alarms)

        if alarms:
            # Save annotated snapshot
            annotated = draw_detections(frame.copy(), alarms, color_map)
            date_str = datetime.now().strftime("%Y-%m-%d")
            snap_dir = Path(snapshot_dir) / date_str
            snap_dir.mkdir(parents=True, exist_ok=True)
            snap_name = f"{task_id}_{int(time.time())}.jpg"
            snap_path = str(snap_dir / snap_name)
            cv2.imwrite(snap_path, annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 85])

            # Base64 for callback
            _, buffer = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            snapshot_b64 = base64.b64encode(buffer).decode("utf-8")

            payload = {
                "task_id": task_id,
                "camera_id": config["camera_id"],
                "algorithm_type": algorithm_type,
                "detections": alarms,
                "snapshot_data": snapshot_b64,
                "snapshot_path": f"{date_str}/{snap_name}",
                "frame_timestamp": datetime.now(timezone.utc).isoformat(),
                "inference_latency_ms": round(latency_ms, 1),
            }

            # Callback
            if callback_url:
                try:
                    resp = httpx.post(
                        callback_url,
                        json=payload,
                        headers={"Authorization": f"Bearer {callback_token}"},
                        timeout=10,
                    )
                    stderr_json(type="callback", task=task_id, status=resp.status_code)
                except Exception as e:
                    stderr_json(type="callback_failed", task=task_id, error=str(e))

            stderr_json(type="detect", task=task_id, count=len(alarms),
                        labels=[d["label"] for d in alarms])

        # Heartbeat every 300 frames
        if frame_count % 300 == 0:
            uptime = time.time() - start_time
            stderr_json(type="heartbeat", task=task_id, fps=round(frame_count / uptime, 1),
                        latency_ms=round(latency_ms, 1), detections=total_detections)

    # Cleanup
    cap.release()
    uptime = time.time() - start_time
    stderr_json(type="shutdown", task=task_id, uptime_sec=round(uptime, 1),
                total_frames=frame_count, total_detections=total_detections)


if __name__ == "__main__":
    main()
