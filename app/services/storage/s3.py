"""S3-compatible backend: Cloudflare R2, Backblaze B2, Wasabi, Supabase, MinIO.

Switching provider is three env vars. R2 is the default recommendation because
it charges nothing for egress, and you will download this dataset many times
during training.
"""

from __future__ import annotations

import time

from app.core.config import Settings
from app.services.storage.base import (
    WAV_CONTENT_TYPE,
    BaseStorage,
    PresignedTarget,
    PresignedUpload,
    StorageError,
)


class S3Storage(BaseStorage):
    def __init__(self, settings: Settings) -> None:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover
            raise StorageError("boto3 is required for STORAGE_BACKEND=s3") from exc

        self.settings = settings
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            # R2 and B2 require SigV4; virtual-host addressing breaks on MinIO.
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def presign_put(
        self, key: str, content_type: str = WAV_CONTENT_TYPE
    ) -> PresignedUpload:
        url = self.client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=self.settings.presign_ttl_s,
        )
        return PresignedUpload(
            url=url,
            method="PUT",
            headers={"Content-Type": content_type},
            key=key,
            expires_at=int(time.time()) + self.settings.presign_ttl_s,
        )

    def presign_get(self, key: str, ttl_s: int | None = None) -> PresignedTarget:
        ttl = ttl_s if ttl_s is not None else self.settings.presign_get_ttl_s
        url = self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=ttl,
        )
        return PresignedTarget(url=url, expires_at=int(time.time()) + ttl)

    def get_bytes(self, key: str) -> bytes:
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f"object not found: {key}") from exc
        return obj["Body"].read()

    def put_bytes(
        self, key: str, data: bytes, content_type: str = WAV_CONTENT_TYPE
    ) -> None:
        self.client.put_object(
            Bucket=self.bucket, Key=key, Body=data, ContentType=content_type
        )

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:  # noqa: BLE001
            return False

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def delete_prefix(self, prefix: str) -> int:
        paginator = self.client.get_paginator("list_objects_v2")
        deleted = 0
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            batch = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if batch:
                self.client.delete_objects(
                    Bucket=self.bucket, Delete={"Objects": batch}
                )
                deleted += len(batch)
        return deleted
