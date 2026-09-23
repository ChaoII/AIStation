"""时间序列接口 controller 测试：upload/list/detail/content/lock/unlock 与鉴权。

与 ``test_audio_event_api.py`` 对应，但按任务要求以「mock service + RustFS + db
会话」的方式隔离：upload 验证 ``db.begin()`` 事务包裹与提交失败时的补偿删除；
content 验证以 ``text/csv`` 返回原始 CSV；其余端点验证返回结构与鉴权。
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _fake_db(fail_commit: bool = False) -> MagicMock:
    """构造一个模拟 async db 会话，``begin()`` 返回可配置成败的异步上下文管理器。"""

    class _BeginCM:
        def __init__(self):
            self._fail = fail_commit

        async def __aenter__(self):
            return None

        async def __aexit__(self, *exc):
            if self._fail:
                raise RuntimeError("commit failed")
            return False

    db = MagicMock()
    db.begin = MagicMock(return_value=_BeginCM())
    return db


def _patch_db_session(monkeypatch, db, module_path: str):
    """让 controller 模块内的 ``async_db_session()`` 产出给定的 mock db。"""
    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=db)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(
        f"{module_path}.async_db_session", MagicMock(return_value=session_cm)
    )


_MODULE = "app.api.v1.module_annotation.dataset.time_series_controller"

_SERIES = {
    "id": 1,
    "dataset_id": 7,
    "name": "data.csv",
    "object_key": "datasets/7/time_series/abc.csv",
    "time_column": "timestamp",
    "value_columns": ["value"],
    "row_count": 3,
    "time_unit": "s",
    "start_time": 1.0,
    "end_time": 3.0,
    "size_bytes": 18,
    "status": "unannotated",
    "locked_by": None,
    "annotation_count": 0,
}


def _upload(test_client: TestClient, auth: dict, dataset_id: int = 7):
    return test_client.post(
        f"/api/v1/annotation/timeseries/upload?dataset_id={dataset_id}",
        files={"file": ("data.csv", b"timestamp,value\n1,10\n2,20\n3,30\n", "text/csv")},
        headers=auth,
    )


def test_upload_success_wraps_transaction_and_returns_metadata(
    test_client, auth_headers, monkeypatch
):
    db = _fake_db()
    _patch_db_session(monkeypatch, db, _MODULE)
    ts = MagicMock()
    ts.object_key = _SERIES["object_key"]
    monkeypatch.setattr(
        "app.api.v1.module_annotation.dataset.time_series_service.TimeSeriesService.upload_time_series",
        AsyncMock(return_value=ts),
    )
    monkeypatch.setattr(
        "app.api.v1.module_annotation.dataset.time_series_service.TimeSeriesService.series_out",
        MagicMock(return_value=_SERIES),
    )
    with patch("app.utils.s3_client.s3_client.delete_object") as delete:
        resp = _upload(test_client, auth_headers, 7)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["id"] == 1
    assert data["time_column"] == "timestamp"
    assert data["value_columns"] == ["value"]
    assert data["row_count"] == 3
    assert data["time_unit"] == "s"
    assert data["size_bytes"] == 18
    # 事务正常提交时不应触发补偿删除
    delete.assert_not_called()


def test_upload_commit_failure_compensates_delete(
    test_client, auth_headers, monkeypatch
):
    # begin() 提交失败（__aexit__ 抛错）时应补偿删除已上传的 RustFS 对象并重新抛错。
    db = _fake_db(fail_commit=True)
    _patch_db_session(monkeypatch, db, _MODULE)
    ts = MagicMock()
    ts.object_key = _SERIES["object_key"]
    monkeypatch.setattr(
        "app.api.v1.module_annotation.dataset.time_series_service.TimeSeriesService.upload_time_series",
        AsyncMock(return_value=ts),
    )
    with patch("app.utils.s3_client.s3_client.delete_object") as delete:
        with pytest.raises(RuntimeError):
            _upload(test_client, auth_headers, 7)
    delete.assert_called_once_with(_SERIES["object_key"])


def test_list_returns_items(test_client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.module_annotation.dataset.time_series_service.TimeSeriesService.list_time_series",
        AsyncMock(return_value=[_SERIES]),
    )
    resp = test_client.get(
        "/api/v1/annotation/timeseries/list?dataset_id=7", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["id"] == 1
    assert items[0]["name"] == "data.csv"


def test_detail_returns_metadata(test_client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.module_annotation.dataset.time_series_service.TimeSeriesService.get_time_series",
        AsyncMock(return_value=_SERIES),
    )
    resp = test_client.get(
        "/api/v1/annotation/timeseries/detail/1", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["id"] == 1
    assert data["dataset_id"] == 7
    assert data["row_count"] == 3
    assert data["start_time"] == 1.0
    assert data["end_time"] == 3.0


def test_content_returns_raw_csv_text(
    test_client, auth_headers, monkeypatch
):
    raw = "timestamp,value\n1,10\n2,20\n3,30\n"
    monkeypatch.setattr(
        "app.api.v1.module_annotation.dataset.time_series_service.TimeSeriesService.get_content",
        AsyncMock(return_value=raw),
    )
    resp = test_client.get(
        "/api/v1/annotation/timeseries/content/1", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert "text/csv" in resp.headers["content-type"]
    assert resp.text == raw


def test_lock_and_unlock(test_client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.module_annotation.dataset.time_series_service.TimeSeriesService.lock_time_series",
        AsyncMock(return_value={"locked": False, "locked_by": 1}),
    )
    lk = test_client.post("/api/v1/annotation/timeseries/lock/1", headers=auth_headers)
    assert lk.status_code == 200, lk.text
    assert lk.json()["data"]["locked"] is False

    monkeypatch.setattr(
        "app.api.v1.module_annotation.dataset.time_series_service.TimeSeriesService.unlock_time_series",
        AsyncMock(return_value=None),
    )
    ulk = test_client.post(
        "/api/v1/annotation/timeseries/unlock/1", headers=auth_headers
    )
    assert ulk.status_code == 200, ulk.text


def test_timeseries_endpoints_require_auth(test_client):
    """所有时间序列端点必须要求登录/权限守卫，未携带凭证返回 401/403。"""
    cases = [
        ("get", "/api/v1/annotation/timeseries/list?dataset_id=1"),
        ("get", "/api/v1/annotation/timeseries/detail/1"),
        ("get", "/api/v1/annotation/timeseries/content/1"),
        ("post", "/api/v1/annotation/timeseries/lock/1"),
        ("post", "/api/v1/annotation/timeseries/unlock/1"),
    ]
    for method, url in cases:
        resp = getattr(test_client, method)(url)
        assert resp.status_code in (401, 403), f"{url} -> {resp.status_code}: {resp.text}"
