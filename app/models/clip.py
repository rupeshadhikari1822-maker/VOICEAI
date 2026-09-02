"""One recorded sentence, its QC verdict, and its review state."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.ids import new_ulid
from app.models.base import Base, utcnow

if TYPE_CHECKING:
    from app.models.session import RecordingSession
    from app.models.speaker import Speaker


class Clip(Base):
    __tablename__ = "clips"
    __table_args__ = (
        Index("ix_clips_qc", "qc_status", "lang"),
        Index("ix_clips_speaker_prompt", "speaker_id", "prompt_id"),
        # The review queue filters on these together, then orders by priority.
        Index("ix_clips_review", "verify_status", "lang", "tombstoned"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_ulid)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    speaker_id: Mapped[str] = mapped_column(ForeignKey("speakers.id"), index=True)
    prompt_id: Mapped[str] = mapped_column(ForeignKey("prompts.id"), index=True)
    # Snapshot of the text as shown. Prompts can be edited; transcripts cannot.
    prompt_text: Mapped[str] = mapped_column(Text)
    lang: Mapped[str] = mapped_column(String(16), index=True)

    object_key: Mapped[str] = mapped_column(String(400), unique=True)
    bytes: Mapped[int | None] = mapped_column(Integer)

    # --- QC, written by app.services.audio_qc from the stored bytes ----
    qc_status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    duration_s: Mapped[float | None] = mapped_column(Float)
    sample_rate: Mapped[int | None] = mapped_column(Integer)
    channels: Mapped[int | None] = mapped_column(Integer)
    bit_depth: Mapped[int | None] = mapped_column(Integer)
    snr_db: Mapped[float | None] = mapped_column(Float)
    peak_dbfs: Mapped[float | None] = mapped_column(Float)
    rms_dbfs: Mapped[float | None] = mapped_column(Float)
    noise_floor_dbfs: Mapped[float | None] = mapped_column(Float)
    clipping_ratio: Mapped[float | None] = mapped_column(Float)
    lead_silence_ms: Mapped[float | None] = mapped_column(Float)
    trail_silence_ms: Mapped[float | None] = mapped_column(Float)
    qc_codes: Mapped[list | None] = mapped_column(JSON)
    qc_reasons: Mapped[list | None] = mapped_column(JSON)
    # Kept only to spot browsers whose numbers drift from the server's.
    client_metrics: Mapped[dict | None] = mapped_column(JSON)

    # --- Human validation (the /review pass) ---------------------------
    # Denormalised current state, for queries. Every change also appends a
    # ReviewEvent, which is the record of how it got here.
    verify_status: Mapped[str] = mapped_column(String(16), default="unverified")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    # A reviewer name, or "asr:<model>" when the pre-filter decided.
    verified_by: Mapped[str | None] = mapped_column(String(80))
    # One of app.services.review.reasons.RejectReason.
    reject_reason: Mapped[str | None] = mapped_column(String(32))
    review_notes: Mapped[str | None] = mapped_column(String(300))
    # Higher sorts first in the queue. Set from ASR uncertainty.
    # server_default matters: without it, adding this NOT NULL column to a
    # table that already has rows fails outright on Postgres.
    review_priority: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", index=True
    )

    # --- ASR pre-filter (scripts/asr_prefilter.py) ----------------------
    # Written even when auto-verifying: a reviewer auditing the auto-pass
    # decisions needs to see what the model actually heard.
    asr_text: Mapped[str | None] = mapped_column(Text)
    asr_cer: Mapped[float | None] = mapped_column(Float)
    asr_model: Mapped[str | None] = mapped_column(String(60))

    # Set by scripts/withdraw.py. Tombstoned clips never export.
    tombstoned: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    session: Mapped["RecordingSession"] = relationship(back_populates="clips")
    speaker: Mapped["Speaker"] = relationship(back_populates="clips")
