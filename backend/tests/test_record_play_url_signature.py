"""录像播放短时签名 URL 测试（替代未鉴权静态路由的回归保护）。"""
import time

from app.api.v1.module_video.record.service import (
    RECORDINGS_DIR,
    build_signed_play_url,
    sign_recording_url,
    verify_recording_signature,
)


def test_sign_and_verify_roundtrip():
    exp = int(time.time()) + 60
    sig = sign_recording_url("cam1", "a.mp4", exp)
    assert verify_recording_signature("cam1", "a.mp4", exp, sig) is True


def test_tampered_and_expired_rejected():
    exp = int(time.time()) + 60
    sig = sign_recording_url("cam1", "a.mp4", exp)
    assert verify_recording_signature("cam2", "a.mp4", exp, sig) is False
    assert verify_recording_signature("cam1", "b.mp4", exp, sig) is False
    assert verify_recording_signature("cam1", "a.mp4", exp, sig[:-1] + "0") is False
    assert verify_recording_signature("cam1", "a.mp4", 0, sig) is False
    old = int(time.time()) - 10
    assert verify_recording_signature("cam1", "a.mp4", old, sign_recording_url("cam1", "a.mp4", old)) is False


def test_static_route_requires_valid_signature(test_client):
    stream_id = "testsignstream"
    file_name = "sample.mp4"
    seg_dir = RECORDINGS_DIR / stream_id
    seg_dir.mkdir(parents=True, exist_ok=True)
    target = seg_dir / file_name
    target.write_bytes(b"\x00\x00\x00\x18ftypmp42")

    try:
        # 无签名 → 403
        assert test_client.get(f"/recordings/{stream_id}/{file_name}").status_code == 403
        # 篡改签名 → 403
        url = build_signed_play_url(stream_id, file_name)
        assert test_client.get(url + "0").status_code == 403
        # 有效签名 → 200
        resp = test_client.get(url)
        assert resp.status_code == 200
        assert resp.content.startswith(b"\x00\x00\x00\x18ftyp")
    finally:
        target.unlink(missing_ok=True)
        try:
            seg_dir.rmdir()
        except OSError:
            pass
