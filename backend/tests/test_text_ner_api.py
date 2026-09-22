"""文档接口 controller 测试：upload/list/detail/content/lock/unlock 与权限校验。

采用与 ``test_video_api.py`` 一致的方式：通过 API 建数据集 + 上传文档（mock
对象存储），再调用接口断言返回结构；``content`` 断言 UTF-8 全文正确返回。
"""
import uuid
from io import BytesIO
from unittest.mock import patch

from fastapi.testclient import TestClient

# 一份中文 UTF-8 文本（含多行），用于验证字符数/行数与 content 全文返回
_TEXT = "这是第一行内容\n第二行中文\n"
_UTF8 = _TEXT.encode("utf-8")


def _create_dataset(test_client: TestClient, auth_headers: dict) -> int:
    resp = test_client.post(
        "/api/v1/annotation/dataset/create",
        json={"name": f"doc-api-{uuid.uuid4().hex[:8]}"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["id"]


def _upload_document(test_client: TestClient, auth_headers: dict, dataset_id: int) -> dict:
    resp = test_client.post(
        f"/api/v1/annotation/document/upload?dataset_id={dataset_id}",
        files={"file": ("doc.txt", _UTF8, "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def test_upload_list_detail_content_lock_unlock(
    test_client: TestClient, auth_headers: dict, monkeypatch
):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    with patch(
        "app.api.v1.module_annotation.dataset.document_service.s3_client.download_fileobj",
        return_value=BytesIO(_UTF8),
    ):
        ds_id = _create_dataset(test_client, auth_headers)
        doc = _upload_document(test_client, auth_headers, ds_id)
        doc_id = doc["id"]
        assert doc["dataset_id"] == ds_id
        assert doc["filename"] == "doc.txt"
        assert doc["encoding"] == "utf-8"
        assert doc["character_count"] == len(_TEXT.encode("utf-16-le")) // 2
        assert doc["line_count"] == _TEXT.count("\n") + 1
        assert doc["status"] == "unannotated"

        # GET /list?dataset_id= -> { items: [...] }
        lst = test_client.get(
            f"/api/v1/annotation/document/list?dataset_id={ds_id}", headers=auth_headers
        )
        assert lst.status_code == 200, lst.text
        items = lst.json()["data"]["items"]
        assert len(items) == 1
        item = items[0]
        assert item["id"] == doc_id
        assert item["dataset_id"] == ds_id
        assert item["encoding"] == "utf-8"
        assert item["status"] == "unannotated"

        # GET /detail/{id} -> 元数据
        det = test_client.get(
            f"/api/v1/annotation/document/detail/{doc_id}", headers=auth_headers
        )
        assert det.status_code == 200, det.text
        assert det.json()["data"]["id"] == doc_id
        assert det.json()["data"]["filename"] == "doc.txt"

        # GET /content/{id} -> text/plain, 返回 UTF-8 全文
        cont = test_client.get(
            f"/api/v1/annotation/document/content/{doc_id}", headers=auth_headers
        )
        assert cont.status_code == 200, cont.text
        assert cont.headers["content-type"].startswith("text/plain")
        assert cont.text == _TEXT

        # POST /lock/{id} -> { locked: False, locked_by }
        lk = test_client.post(
            f"/api/v1/annotation/document/lock/{doc_id}", headers=auth_headers
        )
        assert lk.status_code == 200, lk.text
        assert lk.json()["data"]["locked"] is False

        # POST /unlock/{id} -> 成功
        ulk = test_client.post(
            f"/api/v1/annotation/document/unlock/{doc_id}", headers=auth_headers
        )
        assert ulk.status_code == 200, ulk.text


def test_document_endpoints_require_auth(test_client: TestClient):
    """所有文档端点必须要求登录/权限守卫，未携带凭证返回 401/403。"""
    cases = [
        ("get", "/api/v1/annotation/document/list?dataset_id=1"),
        ("get", "/api/v1/annotation/document/detail/1"),
        ("get", "/api/v1/annotation/document/content/1"),
        ("post", "/api/v1/annotation/document/lock/1"),
        ("post", "/api/v1/annotation/document/unlock/1"),
    ]
    for method, url in cases:
        resp = getattr(test_client, method)(url)
        assert resp.status_code in (401, 403), f"{url} -> {resp.status_code}: {resp.text}"


def test_upload_dataset_not_found(
    test_client: TestClient, auth_headers: dict, monkeypatch
):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    resp = test_client.post(
        "/api/v1/annotation/document/upload?dataset_id=999999",
        files={"file": ("doc.txt", b"hello", "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code == 404
