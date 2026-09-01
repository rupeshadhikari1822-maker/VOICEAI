"""Object storage adapter.

Two backends behind one interface:

  local  ->  ./storage_local, no cloud account needed for development
  s3     ->  any S3-compatible endpoint (Cloudflare R2, Backblaze B2, Wasabi,
             Supabase Storage, MinIO) -- switching provider is three env vars

Audio bytes never pass through the API process. The browser PUTs straight to a
presigned URL, and the server later reads the object back to run QC. The local
backend fakes the same shape with an HMAC-signed upload route so the frontend
code path is identical in development and production.

Object keys carry only the opaque speaker ULID -- never a name, email or phone.
"""

from __future__ import annotations

import hashlib
import hmac
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

from app.config import Settings, get_settings

WAV_CONTENT_TYPE = "audio/wav"


# --- key layout ---------------------------------------------------------
# raw/     the 48 kHz master. Immutable, kept forever.
# derived/ resampled training sets, regenerable from raw.
# consent/ spoken consent, kept apart from the corpus.


def raw_key(lang: str, speaker_id: str, session_id: str, clip_id: str) -> str:
    return f"raw/{lang}/{speaker_id}/{session_id}/{clip_id}.wav"


def derived_key(sr_khz: str, lang: str, speaker_id: str, clip_id: str) -> str:
    return f"derived/{sr_khz}/{lang}/{speaker_id}/{clip_id}.wav"


def consent_key(speaker_id: str, version: str) -> str:
    return f"consent/{speaker_id}/consent_{version}.wav"


@dataclass
class PresignedUpload:
    url: str
    method: str
    headers: dict[str, str]
    key: str
    expires_at: int


class StorageError(RuntimeError):
    pass


class BaseStorage:
    def presign_put(self, key: str, content_type: str = WAV_CONTENT_TYPE) -> PresignedUpload:
        raise NotImplementedError

    def get_bytes(self, key: str) -> bytes:
        raise NotImplementedError

    def put_bytes(self, key: str, data: bytes, content_type: str = WAV_CONTENT_TYPE) -> None:
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError

    def delete_prefix(self, prefix: str) -> int:
        raise NotImplementedError


class LocalStorage(BaseStorage):
    """Filesystem backend for development. Same interface, no cloud account."""

    def __init__(self, settings: Settings) -> None:
        self.root = Path(settings.local_storage_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.settings = settings

    def _path(self, key: str) -> Path:
        # Reject traversal outright rather than sanitising it.
        if key.startswith("/") or ".." in key.split("/"):
            raise StorageError(f"unsafe object key: {key!r}")
        return self.root / key

    def sign(self, key: str, expires_at: int) -> str:
        msg = f"{key}:{expires_at}".encode()
        return hmac.new(
            self.settings.secret_key.encode(), msg, hashlib.sha256
        ).hexdigest()

    def verify(self, key: str, expires_at: int, signature: str) -> bool:
        if expires_at < int(time.time()):
            return False
        return hmac.compare_digest(self.sign(key, expires_at), signature)

    def presign_put(self, key: str, content_type: str = WAV_CONTENT_TYPE) -> PresignedUpload:
        expires_at = int(time.time()) + self.settings.presign_ttl_s
        query = urlencode(
            {"key": key, "expires": expires_at, "sig": self.sign(key, expires_at)}
        )
        return PresignedUpload(
            url=f"{self.settings.public_base_url.rstrip('/')}/api/_local_upload?{query}",
            method="PUT",
            headers={"Content-Type": content_type},
            key=key,
            expires_at=expires_at,
        )

    def get_bytes(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise StorageError(f"object not found: {key}")
        return path.read_bytes()

    def put_bytes(self, key: str, data: bytes, content_type: str = WAV_CONTENT_TYPE) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def delete_prefix(self, prefix: str) -> int:
        target = self._path(prefix)
        if target.is_dir():
            count = sum(1 for p in target.rglob("*") if p.is_file())
            shutil.rmtree(target, ignore_errors=True)
            return count
        if target.is_file():
            target.unlink()
            return 1
        return 0


class S3Storage(BaseStorage):
    """boto3 against any S3-compatible endpoint."""

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

    def presign_put(self, key: str, content_type: str = WAV_CONTENT_TYPE) -> PresignedUpload:
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

    def get_bytes(self, key: str) -> bytes:
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f"object not found: {key}") from exc
        return obj["Body"].read()

    def put_bytes(self, key: str, data: bytes, content_type: str = WAV_CONTENT_TYPE) -> None:
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
                self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": batch})
                deleted += len(batch)
        return deleted


_storage: BaseStorage | None = None


def get_storage() -> BaseStorage:
    global _storage
    if _storage is None:
        settings = get_settings()
        backend = settings.storage_backend.lower()
        if backend == "s3":
            _storage = S3Storage(settings)
        elif backend == "local":
            _storage = LocalStorage(settings)
        else:
            raise StorageError(f"unknown STORAGE_BACKEND: {backend!r}")
    return _storage


def reset_storage() -> None:
    """Test hook -- drops the cached adapter so settings can change."""
    global _storage
    _storage = None
