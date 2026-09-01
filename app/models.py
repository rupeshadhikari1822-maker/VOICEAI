"""SQLAlchemy schema.

The privacy boundary lives here. `Speaker` is the only table holding directly
identifying data, and nothing on it is ever written into an object key, a
filename, a log line or an export. Everything downstream refers to a speaker by
opaque ULID.

`Speaker.caste_ethnicity` is sensitive personal information under Nepal's
Individual Privacy Act 2075 s.27(2). It is nullable, it is never required, and
`scripts/export_dataset.py` has no code path that can emit it.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.ids import new_ulid


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Speaker(Base):
    """A contributor. Holds all PII in the system, and nothing else does."""

    __tablename__ = "speakers"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_ulid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    # --- PII. Never exported, never logged, never in an object key. ----
    name: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(40))

    # --- Sensitive personal information (IPA 2075 s.27(2)). Optional. --
    caste_ethnicity: Mapped[str | None] = mapped_column(String(120))

    # --- Non-identifying attributes. These do get exported. ------------
    age_band: Mapped[str | None] = mapped_column(String(20))
    gender: Mapped[str | None] = mapped_column(String(30))
    # Region, not address. Enough for dialect coverage, useless for tracing.
    province: Mapped[str | None] = mapped_column(String(80))
    district: Mapped[str | None] = mapped_column(String(80))
    municipality: Mapped[str | None] = mapped_column(String(120))
    ward: Mapped[str | None] = mapped_column(String(10))
    mother_tongue: Mapped[str | None] = mapped_column(String(60))
    language_variety: Mapped[str | None] = mapped_column(String(80))
    education: Mapped[str | None] = mapped_column(String(60))

    # --- Withdrawal (scripts/withdraw.py) ------------------------------
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime)

    consents: Mapped[list["ConsentRecord"]] = relationship(
        back_populates="speaker", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["RecordingSession"]] = relationship(back_populates="speaker")
    clips: Mapped[list["Clip"]] = relationship(back_populates="speaker")

    @property
    def is_withdrawn(self) -> bool:
        return self.withdrawn_at is not None

    def export_row(self) -> dict:
        """The only speaker fields allowed to leave the system."""
        return {
            "speaker_id": self.id,
            "age_band": self.age_band,
            "gender": self.gender,
            "province": self.province,
            "district": self.district,
            "mother_tongue": self.mother_tongue,
            "language_variety": self.language_variety,
        }


class ConsentRecord(Base):
    """Documentary proof of consent: a version stamp plus an optional spoken clip."""

    __tablename__ = "consent_records"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_ulid)
    speaker_id: Mapped[str] = mapped_column(
        ForeignKey("speakers.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[str] = mapped_column(String(40))
    # SHA-256 of the exact consent text shown, so we can prove what was agreed to.
    text_sha256: Mapped[str] = mapped_column(String(64))
    accepted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # Separate opt-in. Cannot be retro-fitted, so it is asked before recording.
    commercial_use: Mapped[bool] = mapped_column(Boolean, default=False)
    spoken_clip_key: Mapped[str | None] = mapped_column(String(400))

    speaker: Mapped[Speaker] = relationship(back_populates="consents")


class Prompt(Base):
    """A sentence to be read aloud."""

    __tablename__ = "prompts"
    __table_args__ = (Index("ix_prompts_lang_active", "lang", "active"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    lang: Mapped[str] = mapped_column(String(16), index=True)
    text: Mapped[str] = mapped_column(Text)
    script: Mapped[str] = mapped_column(String(24), default="Deva")
    category: Mapped[str | None] = mapped_column(String(60))
    phonetic_tags: Mapped[list | None] = mapped_column(JSON)
    source: Mapped[str | None] = mapped_column(String(200))
    # Prompts in an unreviewed language land here as False on purpose: a wrong
    # sentence produces a wrong transcript, which is worse than no data.
    active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RecordingSession(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=new_ulid)
    speaker_id: Mapped[str] = mapped_column(ForeignKey("speakers.id"), index=True)
    lang: Mapped[str] = mapped_column(String(16), default="ne")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Device hints help explain a batch of bad takes. No IP, no user id.
    device_hint: Mapped[str | None] = mapped_column(String(300))
    sample_rate: Mapped[int | None] = mapped_column(Integer)

    speaker: Mapped[Speaker] = relationship(back_populates="sessions")
    clips: Mapped[list["Clip"]] = relationship(back_populates="session")


class Clip(Base):
    """One recorded sentence, plus its QC verdict."""

    __tablename__ = "clips"
    __table_args__ = (
        Index("ix_clips_qc", "qc_status", "lang"),
        Index("ix_clips_speaker_prompt", "speaker_id", "prompt_id"),
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

    # --- QC, written by app.audio_qc from the stored bytes -------------
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

    # --- Human validation (the /review pass, not built yet) ------------
    verify_status: Mapped[str] = mapped_column(String(16), default="unverified")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    verified_by: Mapped[str | None] = mapped_column(String(80))

    # Set by scripts/withdraw.py. Tombstoned clips never export.
    tombstoned: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    session: Mapped[RecordingSession] = relationship(back_populates="clips")
    speaker: Mapped[Speaker] = relationship(back_populates="clips")
