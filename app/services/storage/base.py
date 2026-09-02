"""Storage interface shared by every backend.

Audio bytes never pass through the API process. The browser PUTs straight to a
presigned URL, and the server reads the object back to run QC on what actually
landed. Every backend must preserve that property.
"""

from __future__ import annotations

from dataclasses import dataclass

WAV_CONTENT_TYPE = "audio/wav"


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
    def presign_put(
        self, key: str, content_type: str = WAV_CONTENT_TYPE
    ) -> PresignedUpload:
        raise NotImplementedError

    def get_bytes(self, key: str) -> bytes:
        raise NotImplementedError

    def put_bytes(
        self, key: str, data: bytes, content_type: str = WAV_CONTENT_TYPE
    ) -> None:
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError

    def delete_prefix(self, prefix: str) -> int:
        raise NotImplementedError
