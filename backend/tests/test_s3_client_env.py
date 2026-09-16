"""S3Client 环境解析测试。"""
from app.config.setting import settings
from app.utils.s3_client import S3Client


def test_bucket_uses_default_dev(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "dev")
    client = S3Client()
    assert client.default_env == "dev"
    assert client._bucket() == f"{settings.RUSTFS_BUCKET_PREFIX}-dev"


def test_bucket_uses_prod_when_environment_prod(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "prod")
    client = S3Client()
    assert client.default_env == "prod"
    assert client._bucket().endswith("-prod")


def test_bucket_explicit_env_overrides_default(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "prod")
    client = S3Client()
    assert client._bucket("dev").endswith("-dev")
