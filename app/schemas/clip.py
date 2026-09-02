from __future__ import annotations

from pydantic import BaseModel

from app.schemas.common import UploadTarget


class ClipInitIn(BaseModel):
    session_id: str
    prompt_id: str


class ClipInitOut(BaseModel):
    clip_id: str
    object_key: str
    upload: UploadTarget


class ClipCompleteIn(BaseModel):
    # Client metrics are a UX convenience only; the server re-measures.
    client_metrics: dict | None = None


class QCOut(BaseModel):
    clip_id: str
    passed: bool
    codes: list[str]
    reasons: list[str]
    warnings: list[str]
    duration_s: float
    sample_rate: int
    snr_db: float
    peak_dbfs: float
    rms_dbfs: float
    noise_floor_dbfs: float
    clipping_ratio: float
    lead_silence_ms: float
    trail_silence_ms: float
