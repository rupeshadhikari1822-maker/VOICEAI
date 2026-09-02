from __future__ import annotations

from pydantic import BaseModel, Field


class ReviewClipOut(BaseModel):
    """One clip to listen to.

    `qc` metrics and `asr_text` are deliberately NOT in this payload -- see
    app/api/routes/review.py for why they are withheld until after the verdict.
    """

    clip_id: str
    prompt_text: str
    lang: str
    duration_s: float | None = None
    audio_url: str
    audio_expires_at: int


class VerdictIn(BaseModel):
    action: str  # verified | rejected | skipped | unsure
    reason: str | None = None
    notes: str | None = Field(default=None, max_length=300)
    time_spent_ms: int | None = Field(default=None, ge=0)


class VerdictOut(BaseModel):
    clip_id: str
    verify_status: str
    reviewer: str
    # Revealed only now, so it cannot anchor the reviewer's judgement.
    asr_text: str | None = None
    asr_cer: float | None = None
    snr_db: float | None = None
    peak_dbfs: float | None = None


class UndoOut(BaseModel):
    undone: bool
    clip_id: str | None = None
    verify_status: str | None = None


class ReasonOut(BaseModel):
    key: str
    reason: str
    label: str


class ReviewStatsOut(BaseModel):
    reviewer: str
    reviewed_total: int
    reviewed_by_me: int
    pending: int
    rejection_rate: float
    by_reason: dict[str, int]
    median_seconds: float | None = None
    too_fast: int
    agreement_rate: float | None = None
    auto_decided: int
