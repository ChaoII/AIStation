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
