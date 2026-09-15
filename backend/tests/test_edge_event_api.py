"""边缘事件查询接口测试：分页 / 筛选 / 详情 / 鉴权。

事件数据用 Task 2 的 ``record_edge_event`` 落到真实 SQLite 测试库，
接口走 TestClient + admin 鉴权头（复用 conftest 的 test_client/auth_headers）。
"""
import asyncio
import itertools
from uuid import uuid4

import pytest

from app.api.v1.module_video.edge.store import record_edge_event

BASE = "/api/v1/video/edge/event"

# 视频模块限流为 5 次/10 秒，且以 X-Forwarded-For 首值分桶；
# 每个用例用独立转发 IP，避免用例间请求计数互相挤占导致 429。
_IP_SEQ = itertools.count(1)


@pytest.fixture(autouse=True)
def _schema(test_client):
    """启动应用生命周期（建表），接口与落库共用同一测试库。"""
    return test_client


@pytest.fixture
def event_headers(auth_headers):
    """复用 admin 鉴权头，但换上本用例独有的转发 IP（隔离限流桶）。"""
    n = next(_IP_SEQ)
    headers = dict(auth_headers)
    headers["X-Forwarded-For"] = f"10.20.{n // 250}.{n % 250 + 1}"
    return headers


def _objects(label: str = "person") -> list[dict]:
    return [
        {
            "label": label,
            "confidence": 0.9,
            "bbox": {"x": 0.4, "y": 0.4, "width": 0.2, "height": 0.2},
        }
    ]


def _unique_camera() -> int:
    """本用例独占的相机 ID，避免持久化测试库历史行干扰。"""
    return 700000 + int(uuid4().hex[:6], 16) % 100000


def _seed(
    *,
    camera_id: int,
    algo: str = "DET_ZONE",
    task_id: int = 1,
    matched: bool = True,
    label: str = "person",
    ts: float | str = 1000,
    event_id: str | None = None,
    snapshot_ref: str | None = None,
) -> tuple[int | None, str]:
    """落一条事件，返回 (主键 id, event_id)。"""
    eid = event_id or f"ev-{uuid4().hex}"
    event = {
        "event_id": eid,
        "edge_code": "edge-api",
        "camera_id": camera_id,
        "task_id": task_id,
        "algorithm_type": algo,
        "ts": ts,
        "objects": _objects(label),
        "detections": _objects(label),
        "latency_ms": 12.3,
        "snapshot_ref": snapshot_ref,
    }
    row_id = asyncio.run(
        record_edge_event(
            event,
            matched=matched,
            rule_id=7,
            matched_leaves=[{"path": "and/0", "subject": "object_present"}],
        )
    )
    return row_id, eid


def _list(test_client, event_headers, **params):
    return test_client.get(f"{BASE}/list", params=params, headers=event_headers)


def test_list_pagination_shape(test_client, event_headers):
    """分页响应为项目标准结构，并按 page_size 切片、has_next 正确。"""
    cam = _unique_camera()
    ids = {_seed(camera_id=cam)[1] for _ in range(3)}

    data = _list(test_client, event_headers, camera_id=cam, page_no=1, page_size=2).json()["data"]
    assert set(data) >= {"page_no", "page_size", "total", "has_next", "items"}
    assert data["page_no"] == 1
    assert data["page_size"] == 2
    assert data["total"] == 3
    assert data["has_next"] is True
    assert len(data["items"]) == 2
    assert {i["event_id"] for i in data["items"]} <= ids

    page2 = _list(test_client, event_headers, camera_id=cam, page_no=2, page_size=2).json()["data"]
    assert len(page2["items"]) == 1
    assert page2["has_next"] is False


def test_list_filter_camera_algorithm_task(test_client, event_headers):
    """camera_id / algorithm_type / task_id 精确筛选只返回匹配行。"""
    cam = _unique_camera()
    hit = _seed(camera_id=cam, algo="DET_ZONE", task_id=11)[1]
    _seed(camera_id=cam, algo="DET_LINE", task_id=22)

    data = _list(
        test_client, event_headers, camera_id=cam, algorithm_type="DET_ZONE", task_id=11
    ).json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["event_id"] == hit
    assert data["items"][0]["algorithm_type"] == "DET_ZONE"
    assert data["items"][0]["task_id"] == 11


def test_list_filter_matched_false(test_client, event_headers):
    """matched=false 只返回未命中事件。"""
    cam = _unique_camera()
    _seed(camera_id=cam, matched=True)
    miss = _seed(camera_id=cam, matched=False)[1]

    data = _list(test_client, event_headers, camera_id=cam, matched="false").json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["event_id"] == miss
    assert data["items"][0]["matched"] is False


def test_list_filter_time_range(test_client, event_headers):
    """start_time / end_time 区间筛选（边界用宽区间避免时区抖动）。"""
    cam = _unique_camera()
    old = _seed(camera_id=cam, ts=1000)[1]  # 1970-01-01
    new = _seed(camera_id=cam, ts=2000000000)[1]  # 2033-05-18

    after = _list(
        test_client, event_headers, camera_id=cam, start_time="2025-01-01 00:00:00"
    ).json()["data"]
    assert {i["event_id"] for i in after["items"]} == {new}

    before = _list(
        test_client, event_headers, camera_id=cam, end_time="2025-01-01 00:00:00"
    ).json()["data"]
    assert {i["event_id"] for i in before["items"]} == {old}


def test_list_filter_keyword_over_objects(test_client, event_headers):
    """keyword 对 objects 的 label 做模糊匹配。"""
    cam = _unique_camera()
    car = _seed(camera_id=cam, label="car")[1]
    _seed(camera_id=cam, label="person")

    data = _list(test_client, event_headers, camera_id=cam, keyword="car").json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["event_id"] == car
    assert data["items"][0]["labels"] == ["car"]

    empty = _list(test_client, event_headers, camera_id=cam, keyword="不存在的目标").json()["data"]
    assert empty["total"] == 0


def test_detail_returns_full_payload(test_client, event_headers):
    """详情返回全量 objects/detections/matched_leaves，且不含 snapshot_data。"""
    row_id, eid = _seed(camera_id=_unique_camera(), matched=True)

    resp = test_client.get(f"{BASE}/detail/{row_id}", headers=event_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["event_id"] == eid
    assert body["objects"] and body["objects"][0]["label"] == "person"
    assert body["detections"] and body["detections"][0]["label"] == "person"
    assert body["matched"] is True
    assert body["matched_rule_id"] == 7
    assert body["matched_leaves"][0]["subject"] == "object_present"
    assert "snapshot_data" not in body


def test_list_and_detail_expose_snapshot_url(test_client, event_headers, monkeypatch, tmp_path):
    """相对对象 key 命中 DETECTIONS_DIR 时，列表/详情均给出可取图的 snapshot_url。"""
    from app.api.v1.module_video.inference import snapshot as snap

    monkeypatch.setattr(snap.settings, "DETECTIONS_DIR", str(tmp_path))
    f = tmp_path / "raw" / "a.jpg"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"x")

    cam = _unique_camera()
    row_id, _ = _seed(camera_id=cam, snapshot_ref="raw/a.jpg")

    item = _list(test_client, event_headers, camera_id=cam).json()["data"]["items"][0]
    assert item["snapshot_ref"] == "raw/a.jpg"
    assert item["snapshot_url"] == "/api/v1/video/detections/raw/a.jpg"

    detail = test_client.get(f"{BASE}/detail/{row_id}", headers=event_headers).json()["data"]
    assert detail["snapshot_ref"] == "raw/a.jpg"
    assert detail["snapshot_url"] == "/api/v1/video/detections/raw/a.jpg"


def test_snapshot_url_http_passthrough(test_client, event_headers):
    """已是绝对 http(s) URL → snapshot_url 原样返回。"""
    cam = _unique_camera()
    _seed(camera_id=cam, snapshot_ref="https://cdn.example.com/a.jpg")

    item = _list(test_client, event_headers, camera_id=cam).json()["data"]["items"][0]
    assert item["snapshot_ref"] == "https://cdn.example.com/a.jpg"
    assert item["snapshot_url"] == "https://cdn.example.com/a.jpg"


def test_snapshot_url_none_when_missing(test_client, event_headers):
    """无快照引用 → snapshot_url 为 null（snapshot_ref 保持原值）。"""
    cam = _unique_camera()
    _seed(camera_id=cam)

    item = _list(test_client, event_headers, camera_id=cam).json()["data"]["items"][0]
    assert item["snapshot_ref"] is None
    assert item["snapshot_url"] is None


def test_detail_not_found(test_client, event_headers):
    """不存在的事件返回 404。"""
    resp = test_client.get(f"{BASE}/detail/999999999", headers=event_headers)
    assert resp.status_code == 404, resp.text


def test_list_requires_auth(test_client):
    """无鉴权头访问列表被拒绝。"""
    resp = test_client.get(f"{BASE}/list", params={"page_no": 1, "page_size": 1})
    assert resp.status_code in (401, 403), resp.text
