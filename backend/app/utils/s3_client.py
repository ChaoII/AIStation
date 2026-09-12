import io
from typing import BinaryIO

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config.setting import settings


class S3Client:
    """RustFS / S3 兼容对象存储客户端"""

    def __init__(self):
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.RUSTFS_ENDPOINT,
            aws_access_key_id=settings.RUSTFS_ACCESS_KEY,
            aws_secret_access_key=settings.RUSTFS_SECRET_KEY,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )
        self.bucket_prefix = settings.RUSTFS_BUCKET_PREFIX
        self.expiry = settings.RUSTFS_PRESIGNED_URL_EXPIRY
        env = getattr(settings.ENVIRONMENT, "value", settings.ENVIRONMENT)
        self.default_env = "prod" if str(env).lower() == "prod" else "dev"

    def _bucket(self, env: str | None = None) -> str:
        return f"{self.bucket_prefix}-{env or self.default_env}"

    def ensure_bucket(self, env: str | None = None) -> None:
        bucket = self._bucket(env)
        try:
            self.client.head_bucket(Bucket=bucket)
        except ClientError:
            self.client.create_bucket(Bucket=bucket)

    def upload_fileobj(self, fileobj: BinaryIO, object_key: str, env: str | None = None) -> str:
        self.client.upload_fileobj(fileobj, self._bucket(env), object_key)
        return object_key

    def upload_file(self, file_path: str, object_key: str, env: str | None = None) -> str:
        self.client.upload_file(file_path, self._bucket(env), object_key)
        return object_key

    def download_fileobj(self, object_key: str, env: str | None = None) -> io.BytesIO:
        buf = io.BytesIO()
        self.client.download_fileobj(self._bucket(env), object_key, buf)
        buf.seek(0)
        return buf

    def delete_object(self, object_key: str, env: str | None = None) -> None:
        self.client.delete_object(Bucket=self._bucket(env), Key=object_key)

    def object_exists(self, object_key: str, env: str | None = None) -> bool:
        """判断对象是否存在（head_object；不存在或无权访问均视为 False）。"""
        try:
            self.client.head_object(Bucket=self._bucket(env), Key=object_key)
            return True
        except ClientError:
            return False

    def presigned_url(self, object_key: str, env: str | None = None) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket(env), "Key": object_key},
            ExpiresIn=self.expiry,
        )

    def presigned_put_url(self, object_key: str, env: str | None = None) -> str:
        return self.client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self._bucket(env), "Key": object_key},
            ExpiresIn=self.expiry,
        )


s3_client = S3Client()
