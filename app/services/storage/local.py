"""Filesystem backend for development.

Same interface as S3, so the frontend code path is identical in development and
production. Presigned URLs are faked with an HMAC-signed route
(`PUT /api/_local_upload`) that mirrors what a presigned S3 PUT accepts.
"""

from __future__ import annotations

import hashlib
import hmac
import shutil
import time
from pathlib import Path
from urllib.parse import urlencode

from app.core.config import Settings
from app.services.storage.base import (
    WAV_CONTENT_TYPE,
    BaseStorage,
    PresignedUpload,
    StorageError,
)


class LocalStorage(BaseStorage):
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

    def presign_put(
        self, key: str, content_type: str = WAV_CONTENT_TYPE
    ) -> PresignedUpload:
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

    def put_bytes(
        self, key: str, data: bytes, content_type: str = WAV_CONTENT_TYPE
    ) -> None:
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
