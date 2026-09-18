import io
from concurrent.futures import ThreadPoolExecutor
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

    def upload_fileobj(
        self,
        fileobj: BinaryIO,
        object_key: str,
        env: str | None = None,
        content_type: str | None = None,
    ) -> str:
        extra = {"ContentType": content_type} if content_type else None
        self.client.upload_fileobj(fileobj, self._bucket(env), object_key, ExtraArgs=extra)
        return object_key

    def upload_file(
        self,
        file_path: str,
        object_key: str,
        env: str | None = None,
        content_type: str | None = None,
    ) -> str:
        extra = {"ContentType": content_type} if content_type else None
        self.client.upload_file(file_path, self._bucket(env), object_key, ExtraArgs=extra)
        return object_key

    def download_fileobj(self, object_key: str, env: str | None = None) -> io.BytesIO:
        buf = io.BytesIO()
        self.client.download_fileobj(self._bucket(env), object_key, buf)
        buf.seek(0)
        return buf

    def delete_object(self, object_key: str, env: str | None = None) -> None:
        self.client.delete_object(Bucket=self._bucket(env), Key=object_key)

    def delete_objects(
        self,
        keys: list[str],
        env: str | None = None,
        progress_cb=None,
    ) -> int:
        """按 key 批量删除（分片 + 并发），返回请求删除的数量。

        - 不列举前缀：避免大前缀下 ListObjects 超时。
        - 客户端并发：部分 S3 实现（如 RustFS）单请求内串行删除，实测
          并发可提升删除吞吐；``progress_cb(done, total)`` 每完成一片回调。
        """
        if not keys:
            return 0
        bucket = self._bucket(env)
        batch = max(1, settings.RUSTFS_DELETE_BATCH)
        parts = [keys[i:i + batch] for i in range(0, len(keys), batch)]
        workers = max(1, min(settings.RUSTFS_DELETE_CONCURRENCY, len(parts)))
        total = len(keys)
        done = 0

        def _del(part: list[str]) -> int:
            self.client.delete_objects(
                Bucket=bucket,
                Delete={"Objects": [{"Key": k} for k in part], "Quiet": True},
            )
            return len(part)

        with ThreadPoolExecutor(max_workers=workers) as ex:
            for n in ex.map(_del, parts):
                done += n
                if progress_cb:
                    progress_cb(done, total)
        return total

    def delete_prefix(self, prefix: str, env: str | None = None) -> int:
        """删除该前缀下所有对象（列举全部后批量并发删除），返回删除数量。"""
        bucket = self._bucket(env)
        keys: list[str] = []
        token: str | None = None
        while True:
            kwargs: dict = {"Bucket": bucket, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            resp = self.client.list_objects_v2(**kwargs)
            keys += [obj["Key"] for obj in (resp.get("Contents") or [])]
            if not resp.get("IsTruncated"):
                break
            token = resp.get("NextContinuationToken")
        return self.delete_objects(keys, env)

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
