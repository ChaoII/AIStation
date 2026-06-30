ALGORITHM_TYPE_MAP = {
    "INTRUSION":        {"class_name": "UltralyticsDet", "module": "modeldeploy.vision", "desc": "入侵检测"},
    "LINE_CROSSING":    {"class_name": "UltralyticsDet", "module": "modeldeploy.vision", "desc": "越界检测"},
    "CROWD_COUNT":      {"class_name": "UltralyticsDet", "module": "modeldeploy.vision", "desc": "人数统计"},
    "FIRE_SMOKE":       {"class_name": "UltralyticsDet", "module": "modeldeploy.vision", "desc": "烟火检测"},
    "VEHICLE_DETECT":   {"class_name": "UltralyticsDet", "module": "modeldeploy.vision", "desc": "车辆识别"},
    "OBJECT_LEFT":      {"class_name": "UltralyticsDet", "module": "modeldeploy.vision", "desc": "物品遗留"},
    "FACE_DETECT":      {"class_name": "FaceRecognizerPipeline", "module": "modeldeploy.vision", "desc": "人脸识别"},
    "BEHAVIOR_ANALYSIS": {"class_name": "UltralyticsPose", "module": "modeldeploy.vision", "desc": "行为分析"},
}


def create_model(algorithm_type: str, model_path: str, runtime_config: dict | None = None):
    """Lazy import and create a ModelDeploy model instance."""
    import importlib

    info = ALGORITHM_TYPE_MAP.get(algorithm_type)
    if not info:
        raise ValueError(f"Unknown algorithm type: {algorithm_type}")

    mod = importlib.import_module(info["module"])
    model_cls = getattr(mod, info["class_name"])

    from modeldeploy import RuntimeOption

    rt = runtime_config or {}
    option = RuntimeOption()
    gpu_cfg = rt.get("gpu", {})
    engine = rt.get("engine", "onnxruntime")

    if gpu_cfg.get("enabled", False):
        option.use_gpu(gpu_cfg.get("device_id", 0))
    else:
        option.use_cpu()

    option.set_cpu_thread_num(rt.get("threads", 4))
    option.enable_fp16 = rt.get("enable_fp16", False)

    if engine == "tensorrt":
        option.use_trt_backend()
    elif engine == "mnn":
        option.use_mnn_backend()
    else:
        option.use_ort_backend()

    model = model_cls(model_path, option)
    return model
