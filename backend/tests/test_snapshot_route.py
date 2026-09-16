"""快照 HTTP 路由测试。"""
from app.api.v1.module_video.inference import snapshot as snap


def test_snapshot_route_requires_auth(test_client):
    resp = test_client.get("/api/v1/video/detections/none.jpg")
    assert resp.status_code in (401, 403)


def test_snapshot_route_serves_file(test_client, auth_headers, monkeypatch, tmp_path):
    monkeypatch.setattr(snap.settings, "DETECTIONS_DIR", str(tmp_path))
    f = tmp_path / "a.jpg"
    f.write_bytes(b"fake-jpeg-bytes")
    resp = test_client.get("/api/v1/video/detections/a.jpg", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/jpeg")
    assert resp.content == b"fake-jpeg-bytes"


def test_snapshot_route_blocks_traversal(test_client, auth_headers, monkeypatch, tmp_path):
    monkeypatch.setattr(snap.settings, "DETECTIONS_DIR", str(tmp_path))
    resp = test_client.get(
        "/api/v1/video/detections/%2e%2e%2fenv%2f.env.dev", headers=auth_headers
    )
    assert resp.status_code == 404


def test_snapshot_route_missing_404(test_client, auth_headers, monkeypatch, tmp_path):
    monkeypatch.setattr(snap.settings, "DETECTIONS_DIR", str(tmp_path))
    resp = test_client.get("/api/v1/video/detections/nope.jpg", headers=auth_headers)
    assert resp.status_code == 404
