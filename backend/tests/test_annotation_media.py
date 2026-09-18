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

    class _FakeBoto:
        def list_objects_v2(self, **kwargs):
            return pages[kwargs.get("ContinuationToken")]

        def delete_object(self, **kwargs):
            deleted.append(kwargs["Key"])

    client.client = _FakeBoto()
    count = client.delete_prefix("k")
    assert count == 1003
    assert len(deleted) == 1003


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
