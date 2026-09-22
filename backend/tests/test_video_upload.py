from unittest.mock import patch

from app.api.v1.module_annotation.dataset import video_service


def test_probe_video_frame_count():
    with patch.object(video_service, "_run_ffprobe", return_value={
        "streams": [{"width": 1920, "height": 1080, "r_frame_rate": "25/1"}],
        "format": {"duration": "10.0"},
    }):
        info = video_service._probe_video("demo.mp4")
    assert info["width"] == 1920 and info["height"] == 1080
    assert info["fps"] == 25.0
    assert info["duration"] == 10.0
    assert info["frame_count"] == 250


def test_probe_video_guards_bad_rate_and_missing_stream():
    # r_frame_rate 异常（无分母）与缺失视频流时，不应抛错，回退为 0。
    with patch.object(video_service, "_run_ffprobe", return_value={
        "streams": [{"width": 640, "height": 480, "r_frame_rate": "0/1"}],
        "format": {"duration": "5.5"},
    }):
        info = video_service._probe_video("bad.mp4")
    assert info["fps"] == 0.0
    assert info["frame_count"] == 0

    with patch.object(video_service, "_run_ffprobe", return_value={
        "streams": [],
        "format": {},
    }):
        info = video_service._probe_video("empty.mp4")
    assert info["width"] == 0 and info["height"] == 0
    assert info["fps"] == 0.0 and info["duration"] == 0.0
    assert info["frame_count"] == 0


def test_run_ffprobe_returns_parsed_json():
    # 真实子进程解析：用 ffprobe 探测一个有效 mp4 应返回可 JSON 解析的 dict。
    import json
    import subprocess
    import tempfile
    from pathlib import Path

    # 生成一个 1 秒 160x90 的短视频（用 ffformate 生成的原始帧不依赖视频编码即可被
    # ffprobe 识别）。先尝试用 ffmpeg 合成，失败则跳过该冒烟测试。
    probe_ok = subprocess.run(
        ["ffprobe", "-version"], capture_output=True, text=True, check=False
    ).returncode == 0
    if not probe_ok:
        return
    try:
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
             "-i", "testsrc=duration=1:size=160x90:rate=25",
             "-pix_fmt", "yuv420p", "-y", str(Path(tempfile.gettempdir()) / "vf_probe.mp4")],
            capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return
    path = str(Path(tempfile.gettempdir()) / "vf_probe.mp4")
    data = video_service._run_ffprobe(path)
    assert isinstance(data, dict)
    assert "streams" in data and "format" in data
    # 能正确解析出 JSON（非字符串）
    assert isinstance(json.dumps(data), str)
    assert data["streams"]
