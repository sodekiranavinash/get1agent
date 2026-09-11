from __future__ import annotations

import os


class Storage:
    """S3 in production, local disk when ``S3_BUCKET`` is unset."""

    def __init__(
        self,
        bucket: str | None = None,
        region: str | None = None,
        local_root: str | None = None,
    ) -> None:
        self.bucket = bucket if bucket is not None else (os.environ.get("S3_BUCKET") or None)
        self.region = (
            region
            or os.environ.get("S3_REGION")
            or os.environ.get("AWS_REGION")
        )
        self.local_root = local_root or os.environ.get(
            "LOCAL_STORAGE_DIR", "local/.storage"
        )
        self._client = None

    @property
    def mode(self) -> str:
        return "s3" if self.bucket else "local"

    def _s3(self):
        if self._client is None:
            import boto3
            from botocore.config import Config

            # Virtual-hosted addressing makes boto3 sign against the bucket's
            # regional endpoint instead of the global s3.amazonaws.com one.
            self._client = boto3.client(
                "s3",
                region_name=self.region,
                config=Config(s3={"addressing_style": "virtual"}),
            )
        return self._client

    def _path(self, key: str) -> str:
        return os.path.join(self.local_root, key)

    def put_bytes(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> None:
        if self.mode == "s3":
            self._s3().put_object(
                Bucket=self.bucket, Key=key, Body=data, ContentType=content_type
            )
            return
        path = self._path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(data)

    def get_bytes(self, key: str) -> bytes:
        if self.mode == "s3":
            response = self._s3().get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()
        with open(self._path(key), "rb") as handle:
            return handle.read()

    def head_size(self, key: str) -> int:
        if self.mode == "s3":
            response = self._s3().head_object(Bucket=self.bucket, Key=key)
            return int(response["ContentLength"])
        path = self._path(key)
        return os.path.getsize(path) if os.path.exists(path) else 0

    def delete(self, key: str) -> None:
        if self.mode == "s3":
            self._s3().delete_object(Bucket=self.bucket, Key=key)
            return
        path = self._path(key)
        if os.path.exists(path):
            os.remove(path)
