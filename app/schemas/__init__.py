"""Pydantic request/response models, grouped by resource.

Re-exported flat so `from app import schemas` then `schemas.SpeakerIn` keeps
working exactly as it did before the split.
"""

from __future__ import annotations

from app.schemas.clip import (
    ClipCompleteIn,
    ClipInitIn,
    ClipInitOut,
    QCOut,
)
from app.schemas.common import UploadTarget
from app.schemas.consent import ConsentIn, SpokenConsentInitOut
from app.schemas.prompt import PromptOut
from app.schemas.session import ProgressOut, SessionIn, SessionOut
from app.schemas.speaker import SpeakerIn, SpeakerOut

__all__ = [
    "ClipCompleteIn",
    "ClipInitIn",
    "ClipInitOut",
    "ConsentIn",
    "ProgressOut",
    "PromptOut",
    "QCOut",
    "SessionIn",
    "SessionOut",
    "SpeakerIn",
    "SpeakerOut",
    "SpokenConsentInitOut",
    "UploadTarget",
]
