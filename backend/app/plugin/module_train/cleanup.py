"""定时清理临时训练产物目录。"""
import asyncio
import os
import shutil
import tempfile
import time


async def cleanup_loop(keep_days: int = 7, interval_sec: int = 3600):
    while True:
        try:
            base = tempfile.gettempdir()
            for sub in ("train_output", "eval_output", "predict_output", "deploy_output", "model_export", "dataset_export", "model_export_logs"):
                d = os.path.join(base, sub)
                if not os.path.isdir(d):
                    continue
                cutoff = time.time() - keep_days * 86400
                for entry in os.listdir(d):
                    p = os.path.join(d, entry)
                    try:
                        if os.path.getmtime(p) < cutoff:
                            if os.path.isdir(p):
                                shutil.rmtree(p, ignore_errors=True)
                            else:
                                os.remove(p)
                    except Exception:
                        pass
        except Exception:
            pass
        await asyncio.sleep(interval_sec)
