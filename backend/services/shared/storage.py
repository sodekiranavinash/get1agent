from __future__ import annotations

import os


class Storage:
    """S3 object storage. ``S3_BUCKET`` is required."""

    def __init__(
        self,
        bucket: str | None = None,
        region: str | None = None,
    ) -> None:
        self.bucket = bucket if bucket is not None else (os.environ.get("S3_BUCKET") or "")
        if not self.bucket:
            raise RuntimeError("S3_BUCKET is required")
        self.region = (
            region
            or os.environ.get("S3_REGION")
            or os.environ.get("AWS_REGION")
        )
        self._client = None

    @property
    def mode(self) -> str:
        return "s3"

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

    def put_bytes(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> None:
        self._s3().put_object(
            Bucket=self.bucket, Key=key, Body=data, ContentType=content_type
        )

    def get_bytes(self, key: str) -> bytes:
        response = self._s3().get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()

    def head_size(self, key: str) -> int:
        response = self._s3().head_object(Bucket=self.bucket, Key=key)
        return int(response["ContentLength"])

    def delete(self, key: str) -> None:
        self._s3().delete_object(Bucket=self.bucket, Key=key)
