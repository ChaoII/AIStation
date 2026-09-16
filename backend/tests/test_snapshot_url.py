"""快照引用归一化测试。"""
from pathlib import Path

from app.api.v1.module_video.inference import snapshot as snap


def test_empty_returns_none():
    assert snap.resolve_snapshot_url(None) is None
    assert snap.resolve_snapshot_url("") is None
    assert snap.resolve_snapshot_url("   ") is None


def test_http_passthrough():
    url = "https://cdn.example.com/a.jpg"
    assert snap.resolve_snapshot_url(url) == url


def test_object_scheme_presign(monkeypatch):
    monkeypatch.setattr(snap, "_presign", lambda key: f"https://signed/{key}")
    assert snap.resolve_snapshot_url("s3://edge-01/cam7/a.jpg") == "https://signed/edge-01/cam7/a.jpg"


def test_local_absolute(monkeypatch, tmp_path):
    monkeypatch.setattr(snap.settings, "DETECTIONS_DIR", str(tmp_path))
    f = tmp_path / "2026-09-12" / "a.jpg"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"x")
    assert snap.resolve_snapshot_url(str(f)) == "/api/v1/video/detections/2026-09-12/a.jpg"


def test_local_relative(monkeypatch, tmp_path):
    monkeypatch.setattr(snap.settings, "DETECTIONS_DIR", str(tmp_path))
    f = tmp_path / "2026-09-12" / "b.jpg"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"x")
    assert snap.resolve_snapshot_url("2026-09-12/b.jpg") == "/api/v1/video/detections/2026-09-12/b.jpg"


def test_missing_relative_becomes_presign(monkeypatch, tmp_path):
    monkeypatch.setattr(snap.settings, "DETECTIONS_DIR", str(tmp_path))
    monkeypatch.setattr(snap, "_presign", lambda key: f"https://signed/{key}")
    assert snap.resolve_snapshot_url("edge-01/cam7/missing.jpg") == "https://signed/edge-01/cam7/missing.jpg"


def test_presign_failure_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(snap.settings, "DETECTIONS_DIR", str(tmp_path))
    monkeypatch.setattr(snap, "_presign", lambda key: None)
    assert snap.resolve_snapshot_url("edge-01/cam7/missing.jpg") is None


def test_safe_local_snapshot_blocks_traversal(monkeypatch, tmp_path):
    monkeypatch.setattr(snap.settings, "DETECTIONS_DIR", str(tmp_path))
    assert snap.safe_local_snapshot("../secret.txt") is None
    assert snap.safe_local_snapshot(str(Path(tmp_path).parent / "secret.txt")) is None


def test_safe_local_snapshot_ok(monkeypatch, tmp_path):
    monkeypatch.setattr(snap.settings, "DETECTIONS_DIR", str(tmp_path))
    f = tmp_path / "a.jpg"
    f.write_bytes(b"x")
    assert snap.safe_local_snapshot("a.jpg") == f.resolve()


def test_safe_detections_path_blocks_traversal(monkeypatch, tmp_path):
    """写盘路径解析：``../`` 与越界绝对路径必须被拒绝（不要求文件存在）。"""
    monkeypatch.setattr(snap.settings, "DETECTIONS_DIR", str(tmp_path))
    assert snap.safe_detections_path("../../evil.jpg") is None
    assert snap.safe_detections_path(str(Path(tmp_path).parent / "evil.jpg")) is None
    assert snap.safe_detections_path("") is None


def test_safe_detections_path_allows_nested_relative(monkeypatch, tmp_path):
    """合法的子目录相对路径应归一化到 DETECTIONS_DIR 内。"""
    monkeypatch.setattr(snap.settings, "DETECTIONS_DIR", str(tmp_path))
    assert snap.safe_detections_path("2026-09-12/a.jpg") == (tmp_path / "2026-09-12" / "a.jpg").resolve()
