"""Object storage: backend selection plus the shared surface.

Import everything storage-related from here. `from app.services.storage import
get_storage, raw_key, StorageError` covers every call site in the codebase.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.services.storage.base import (
    WAV_CONTENT_TYPE,
    BaseStorage,
    PresignedUpload,
    StorageError,
)
from app.services.storage.keys import consent_key, derived_key, raw_key
from app.services.storage.local import LocalStorage
from app.services.storage.s3 import S3Storage

__all__ = [
    "BaseStorage",
    "LocalStorage",
    "PresignedUpload",
    "S3Storage",
    "StorageError",
    "WAV_CONTENT_TYPE",
    "consent_key",
    "derived_key",
    "get_storage",
    "raw_key",
    "reset_storage",
]

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
