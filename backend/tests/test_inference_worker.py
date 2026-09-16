"""推理 worker 纯逻辑与 PID 防重测试。"""
import os
from datetime import datetime

from app.api.v1.module_video.inference import scheduler as sch
from app.api.v1.module_video.inference import worker as w


def test_within_schedule_empty_is_true():
    assert w.within_schedule(None, datetime(2026, 1, 1, 3, 0)) is True
    assert w.within_schedule({}, datetime(2026, 1, 1, 3, 0)) is True


def test_within_schedule_range():
    cfg = {"start": "08:00", "end": "18:00", "days": [0, 1, 2, 3, 4]}
    mon = datetime(2026, 1, 5, 12, 0)  # 周一
    assert w.within_schedule(cfg, mon) is True
    assert w.within_schedule(cfg, datetime(2026, 1, 5, 20, 0)) is False


def test_within_schedule_slots():
    # 实际前端下发格式：{type:weekly, slots:[{day,start,end}]}，start/end 为整点小时
    cfg = {"type": "weekly", "slots": [{"day": 0, "start": 8, "end": 18}]}
    assert w.within_schedule(cfg, datetime(2026, 1, 5, 12, 0)) is True
    assert w.within_schedule(cfg, datetime(2026, 1, 5, 20, 0)) is False
    assert w.within_schedule(cfg, datetime(2026, 1, 6, 12, 0)) is False  # 周二不在时段


def test_within_schedule_ranges_and_invalid():
    cfg = {"ranges": [["08:00", "12:00"], ["14:00", "18:00"]]}
    assert w.within_schedule(cfg, datetime(2026, 1, 5, 10, 0)) is True
    assert w.within_schedule(cfg, datetime(2026, 1, 5, 13, 0)) is False
    # 解析失败 → True（不误停）
    assert w.within_schedule("{not json", datetime(2026, 1, 5, 3, 0)) is True


def test_sensitivity_to_conf():
    assert w.sensitivity_to_conf(50) == 0.5
    assert w.sensitivity_to_conf(100) < 0.5
    assert w.sensitivity_to_conf(0) > 0.5
    assert 0.05 <= w.sensitivity_to_conf(1000) <= 0.95


def test_label_name():
    class R:
        label = "person"
        label_id = 0

    assert w.label_name(R()) == "person"

    class R2:
        label = None
        label_id = 2

    assert w.label_name(R2(), ["a", "b", "car"]) == "car"
    assert w.label_name(R2()) == "2"


def test_is_worker_alive_rejects_non_worker():
    # 当前 pytest 进程 cmdline 不含 worker.py
    assert sch.is_worker_alive(os.getpid()) is False
    assert sch.is_worker_alive(999999999) is False


def test_pidfile_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(sch, "CONFIG_DIR", tmp_path)
    assert sch.read_worker_pid(7) is None
    sch.write_worker_pid(7, 12345)
    assert sch.read_worker_pid(7) == 12345
    sch.clear_worker_pid(7)
    assert sch.read_worker_pid(7) is None
