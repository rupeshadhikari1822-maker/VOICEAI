from __future__ import annotations

from pydantic import BaseModel

from app.schemas.common import UploadTarget


class ConsentIn(BaseModel):
    version: str
    accepted: bool
    # The active consent requires commercial assignment for participation.
    commercial_use: bool = False


class SpokenConsentInitOut(BaseModel):
    object_key: str
    upload: UploadTarget
