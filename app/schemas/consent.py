from __future__ import annotations

from pydantic import BaseModel

from app.schemas.common import UploadTarget


class ConsentIn(BaseModel):
    version: str
    accepted: bool
    # Separate opt-in. Asked before recording because it cannot be added later.
    commercial_use: bool = False


class SpokenConsentInitOut(BaseModel):
    object_key: str
    upload: UploadTarget
