from __future__ import annotations

import json
import os
from typing import Any


class PreconditionFailed(Exception):
    """Raised when a conditional S3 write loses an ``If-Match`` race."""


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

    def get_text(self, key: str) -> str:
        return self.get_bytes(key).decode("utf-8")

    def put_json(self, key: str, value: Any) -> None:
        self.put_bytes(
            key,
            json.dumps(value, default=str).encode("utf-8"),
            "application/json",
        )

    def get_json(self, key: str) -> Any | None:
        try:
            return json.loads(self.get_text(key))
        except Exception:  # noqa: BLE001 - missing/corrupt object
            return None

    def get_json_with_etag(self, key: str) -> tuple[Any | None, str | None]:
        """Read a JSON object together with its ETag (``None`` when absent)."""
        from botocore.exceptions import ClientError

        try:
            response = self._s3().get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {
                "NoSuchKey",
                "404",
                "NotFound",
            }:
                return None, None
            raise
        body = response["Body"].read()
        etag = response.get("ETag")
        etag = etag.strip('"') if etag else None
        try:
            return json.loads(body), etag
        except ValueError:
            return None, etag

    def head(self, key: str) -> dict[str, Any] | None:
        try:
            return self._s3().head_object(Bucket=self.bucket, Key=key)
        except Exception:  # noqa: BLE001 - missing object
            return None

    def head_size(self, key: str) -> int:
        response = self.head(key)
        if response is None:
            raise FileNotFoundError(key)
        return int(response["ContentLength"])

    def head_etag(self, key: str) -> str | None:
        response = self.head(key)
        if response is None:
            return None
        etag = response.get("ETag")
        return etag.strip('"') if etag else None

    def put_json_conditional(
        self, key: str, value: Any, etag: str | None
    ) -> str:
        """Conditional JSON write; returns the new ETag.

        A new object is created only when ``etag`` is ``None`` (``If-None-Match``),
        otherwise the write only succeeds if the current ETag still matches.
        """
        body = json.dumps(value, default=str).encode("utf-8")
        kwargs: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": key,
            "Body": body,
            "ContentType": "application/json",
        }
        if etag is None:
            kwargs["IfNoneMatch"] = "*"
        else:
            kwargs["IfMatch"] = etag
        try:
            response = self._s3().put_object(**kwargs)
        except Exception as exc:  # noqa: BLE001
            from botocore.exceptions import ClientError

            if (
                isinstance(exc, ClientError)
                and exc.response.get("Error", {}).get("Code")
                in {"PreconditionFailed", "412"}
            ):
                raise PreconditionFailed(key) from exc
            raise
        new_etag = response.get("ETag")
        return new_etag.strip('"') if new_etag else ""

    def presign_put(self, key: str, content_type: str, expires_in: int = 3600) -> str:
        return self._s3().generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=expires_in,
        )

    def presign_get(self, key: str, expires_in: int = 3600) -> str | None:
        return self._s3().generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    def delete(self, key: str) -> None:
        self._s3().delete_object(Bucket=self.bucket, Key=key)

    def delete_many(self, keys: list[str]) -> None:
        if not keys:
            return
        client = self._s3()
        for start in range(0, len(keys), 1000):
            batch = keys[start : start + 1000]
            client.delete_objects(
                Bucket=self.bucket,
                Delete={"Objects": [{"Key": key} for key in batch]},
            )

    def list_keys(self, prefix: str) -> list[str]:
        client = self._s3()
        keys: list[str] = []
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            keys.extend(item["Key"] for item in page.get("Contents", []))
        return keys

    def delete_prefix(self, prefix: str) -> None:
        """Delete every object under ``prefix`` (original + derived artifacts)."""
        client = self._s3()
        bucket = self.bucket
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            if objects:
                client.delete_objects(Bucket=bucket, Delete={"Objects": objects})
