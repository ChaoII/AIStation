"""数据集 purge 与缩略图列测试。"""


def test_annotation_image_has_thumbnail_key(test_client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    from app.api.v1.module_annotation.dataset.model import AnnotationImageModel

    assert hasattr(AnnotationImageModel, "thumbnail_key")
