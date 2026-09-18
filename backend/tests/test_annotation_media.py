"""媒体管线与 S3 客户端测试。"""
import io


def test_delete_prefix_paginates(monkeypatch):
    """delete_prefix 必须翻页删除全部对象（>1000 时不能只删第一页）。"""
    from app.utils.s3_client import S3Client

    client = S3Client.__new__(S3Client)  # 不跑 __init__，避免真实 boto3 连接
    client.bucket_prefix = "test"
    client.default_env = "dev"

    pages = {
        None: {"Contents": [{"Key": f"k{i}"} for i in range(1000)], "IsTruncated": True,
               "NextContinuationToken": "t1"},
        "t1": {"Contents": [{"Key": f"z{i}"} for i in range(3)], "IsTruncated": False},
    }
    deleted: list[str] = []
    batch_calls = 0

    class _FakeBoto:
        def list_objects_v2(self, **kwargs):
            return pages[kwargs.get("ContinuationToken")]

        def delete_objects(self, **kwargs):
            nonlocal batch_calls
            batch_calls += 1
            deleted.extend(o["Key"] for o in kwargs["Delete"]["Objects"])

    client.client = _FakeBoto()
    count = client.delete_prefix("k")
    assert count == 1003
    assert sorted(deleted) == sorted(
        [f"k{i}" for i in range(1000)] + [f"z{i}" for i in range(3)]
    )
    # 分片并发批量删除（非逐对象）
    assert batch_calls >= 2


def test_upload_fileobj_passes_content_type(monkeypatch):
    """upload_fileobj 需把 content_type 透传到 ExtraArgs。"""
    from app.utils.s3_client import S3Client

    client = S3Client.__new__(S3Client)
    client.bucket_prefix = "test"
    client.default_env = "dev"
    captured: dict = {}

    class _FakeBoto:
        def upload_fileobj(self, fileobj, bucket, key, ExtraArgs=None):
            captured["bucket"] = bucket
            captured["key"] = key
            captured["extra"] = ExtraArgs

    client.client = _FakeBoto()
    client.upload_fileobj(io.BytesIO(b"x"), "a/b.png", content_type="image/png")
    assert captured["extra"] == {"ContentType": "image/png"}


def _png_bytes(w: int, h: int) -> bytes:
    import io as _io
    from PIL import Image

    buf = _io.BytesIO()
    Image.new("RGB", (w, h), (200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


def test_process_image_returns_dims_and_thumbnail():
    from app.api.v1.module_annotation.dataset.media import process_image

    w, h, thumb = process_image(_png_bytes(1200, 600))
    assert (w, h) == (1200, 600)
    assert thumb is not None
    from PIL import Image
    import io as _io

    with Image.open(_io.BytesIO(thumb)) as t:
        assert t.format == "JPEG"
        assert max(t.size) <= 512


def test_process_image_bad_bytes_returns_none_thumb():
    from app.api.v1.module_annotation.dataset.media import process_image

    w, h, thumb = process_image(b"not-an-image")
    assert (w, h, thumb) == (0, 0, None)


def test_content_type_mapping():
    from app.api.v1.module_annotation.dataset.media import content_type_for

    assert content_type_for(".png") == "image/png"
    assert content_type_for(".JPG") == "image/jpeg"
    assert content_type_for(".unknown") == "application/octet-stream"


def test_upload_generates_thumbnail_and_content_type(test_client, auth_headers, monkeypatch):
    from uuid import uuid4

    uploaded: list[tuple[str, dict]] = []
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)

    def _capture(fileobj, object_key, env=None, content_type=None):
        uploaded.append((object_key, {"content_type": content_type}))
        return object_key

    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", _capture)

    ds = test_client.post("/api/v1/annotation/dataset/create",
                          json={"name": f"media-{uuid4().hex[:8]}"},
                          headers=auth_headers).json()["data"]
    ds_id = ds["id"]
    png = _png_bytes(800, 400)
    r = test_client.post(
        f"/api/v1/annotation/dataset/{ds_id}/upload",
        files={"files": ("a.png", png, "image/png")},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["uploaded_count"] == 1
    keys = [k for k, _ in uploaded]
    assert any(k.startswith(f"datasets/{ds_id}/images/") for k in keys)
    assert any(k.startswith(f"datasets/{ds_id}/thumbnails/") for k in keys)
    thumb = [meta for k, meta in uploaded if "/thumbnails/" in k][0]
    assert thumb["content_type"] == "image/jpeg"


def test_upload_rejects_bad_extension(test_client, auth_headers, monkeypatch):
    from uuid import uuid4

    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    ds = test_client.post("/api/v1/annotation/dataset/create",
                          json={"name": f"bad-{uuid4().hex[:8]}"},
                          headers=auth_headers).json()["data"]
    r = test_client.post(
        f"/api/v1/annotation/dataset/{ds['id']}/upload",
        files={"files": ("a.exe", b"MZ", "application/octet-stream")},
        headers=auth_headers,
    )
    assert r.status_code == 400, r.text


def test_upload_broken_image_registers_without_thumbnail(test_client, auth_headers, monkeypatch):
    from uuid import uuid4

    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    ds = test_client.post("/api/v1/annotation/dataset/create",
                          json={"name": f"part-{uuid4().hex[:8]}"},
                          headers=auth_headers).json()["data"]
    r = test_client.post(
        f"/api/v1/annotation/dataset/{ds['id']}/upload",
        files=[
            ("files", ("good.png", _png_bytes(10, 10), "image/png")),
            ("files", ("bad.png", b"broken", "image/png")),
        ],
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["uploaded_count"] == 2   # 坏图仍登记（无缩略图），不阻断
    assert data["failed_count"] == 0
    by_name = {u["filename"]: u for u in data["uploaded"]}
    assert by_name["good.png"]["thumbnail_key"]
    assert by_name["bad.png"]["thumbnail_key"] is None


def test_get_images_includes_thumbnail_url(test_client, auth_headers, monkeypatch):
    from uuid import uuid4

    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    monkeypatch.setattr(
        "app.utils.s3_client.s3_client.presigned_url",
        lambda key, *a, **k: f"http://fake/{key}",
    )
    ds = test_client.post("/api/v1/annotation/dataset/create",
                          json={"name": f"url-{uuid4().hex[:8]}"},
                          headers=auth_headers).json()["data"]
    test_client.post(
        f"/api/v1/annotation/dataset/{ds['id']}/upload",
        files={"files": ("a.png", _png_bytes(20, 20), "image/png")},
        headers=auth_headers,
    )
    items = test_client.get(
        f"/api/v1/annotation/dataset/{ds['id']}/images", headers=auth_headers
    ).json()["data"]["items"]
    assert items[0]["thumbnail_key"]
    assert items[0]["thumbnail_url"].startswith("http://fake/")
